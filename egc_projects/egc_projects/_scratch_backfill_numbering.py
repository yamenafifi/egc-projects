"""One-time maintenance after the code_naming.py format fix (project-prefixed, single-letter-
discipline codes matching the real client MDR convention — see that module's docstring). Two
things this script does, both safe to re-run (idempotent) and safe to run on any site regardless
of what data it holds:

1. Corrects the 3 EGC Document Type / EGC Submittal Type `abbreviation` values that `install.py`
   seeded with the OLD convention before this fix (Drawing: DWG->SD, Technical Data: TD->MSF,
   Material Submittal: MAT->MSF) — `install.py`'s own seed loop only ever inserts, never
   overwrites an existing row, so a site that already ran it once needs this direct correction.
   `install.py`'s tuples are already updated so a *fresh* site never needs this step.

2. Backfills the `Series` counters `code_naming.py` reads, so a NEW Document/Submittal on a
   project that already has real (e.g. imported) numbers continues from the correct next
   sequence instead of restarting at 001 and colliding. Computed by grouping every existing
   Document/Submittal by its real (project, discipline, type) fields — not by re-parsing the
   type/discipline letters embedded in its own number string, which can legitimately disagree
   with the fields (seen once in the Siemens import: a document numbered "...-M-001" whose
   `discipline` field is actually ELEC) — and taking the highest trailing sequence per group.
   Only ever raises a counter, never lowers one, so re-running after new documents exist is safe.

   Gated on `code_naming._CODE_PATTERN` (the full `prefix-TYPE-DISC-seq` shape) before trusting a
   number's trailing digits as a real sequence — not a loose trailing-digit match. Caught during
   dev testing: the demo project (PRJ2601051) has its own hand-crafted legacy numbers like
   "M-104" that a loose `-(\\d+)$` match would misread as sequence 104 in a brand-new scheme that
   project has never actually used, inflating its counter for no reason. The full-shape gate
   skips those correctly (no `-TYPE-DISC-` middle to match).
"""

import frappe

from egc_projects.egc_projects.code_naming import _CODE_PATTERN, _document_series_key, _submittal_series_key

ABBREVIATION_FIXES = (
	("EGC Document Type", "Drawing", "SD"),
	("EGC Document Type", "Technical Data", "MSF"),
	("EGC Submittal Type", "Material Submittal", "MSF"),
)


def _fix_abbreviations():
	for doctype, name, abbr in ABBREVIATION_FIXES:
		if not frappe.db.exists(doctype, name):
			continue
		current = frappe.db.get_value(doctype, name, "abbreviation")
		if current == abbr:
			print(f"{doctype} {name}: already {abbr}")
			continue
		frappe.db.set_value(doctype, name, "abbreviation", abbr, update_modified=False)
		print(f"{doctype} {name}: {current} -> {abbr}")


def _backfill_series(doctype, number_field, type_field, type_doctype, series_key_fn):
	rows = frappe.get_all(doctype, fields=["project", "discipline", type_field, number_field])
	type_abbrs = {r.name: r.abbreviation for r in frappe.get_all(type_doctype, fields=["name", "abbreviation"])}

	max_seq = {}
	for row in rows:
		number = row.get(number_field)
		discipline = row.get("discipline")
		type_value = row.get(type_field)
		project = row.get("project")
		if not (number and discipline and type_value and project):
			continue
		abbr = type_abbrs.get(type_value)
		if not abbr:
			continue
		match = _CODE_PATTERN.match(number)
		if not match:
			continue
		seq = int(match.group("seq"))
		key = series_key_fn(project, discipline, abbr)
		max_seq[key] = max(max_seq.get(key, 0), seq)

	for key, seq in sorted(max_seq.items()):
		existing = frappe.db.sql("SELECT `current` FROM `tabSeries` WHERE `name`=%s", (key,))
		existing_val = existing[0][0] if existing else None
		if existing_val is None:
			frappe.db.sql("INSERT INTO `tabSeries` (`name`, `current`) VALUES (%s, %s)", (key, seq))
			print(f"seeded {key} = {seq}")
		elif seq > existing_val:
			frappe.db.sql("UPDATE `tabSeries` SET `current`=%s WHERE `name`=%s", (seq, key))
			print(f"raised {key}: {existing_val} -> {seq}")
		else:
			print(f"left {key} at {existing_val} (observed max {seq})")


def run():
	_fix_abbreviations()
	_backfill_series("EGC Project Document", "document_number", "document_type", "EGC Document Type", _document_series_key)
	_backfill_series("EGC Submittal", "submittal_number", "submittal_type", "EGC Submittal Type", _submittal_series_key)
	frappe.db.commit()
