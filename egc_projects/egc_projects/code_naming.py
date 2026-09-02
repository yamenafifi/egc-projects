# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Discipline/Type-aware smart codes for Activity/Document/Submittal (docs/ARCHITECTURE.md). WBS
is deliberately out of scope — `EGC WBS Node.wbs_code` stays fully manual.

The code field (`activity_code`/`document_number`/`submittal_number`) is **not directly
user-editable** — Discipline (+ Type, for Document/Submittal) are the only things a person picks;
the code itself is server-generated. Two halves:

- A "peek" (`suggest_*`, whitelisted) is a plain, lock-free read of `Series.current` — never
  mutates anything — used purely to preview a value live while a Hub dialog is still open and may
  never be submitted.
- An "assign" (`assign_*_code`, called from each doctype's own `before_insert()`) is the one
  place a code is actually decided, via the real `frappe.model.naming.getseries()` — the exact
  primitive behind every native `naming_series:` doctype (e.g. ERPNext's Sales Invoice
  `SINV-.YYYY.-`). It only fires **if the field is still blank** at insert time — this is what
  lets the Hub's own bulk Import feature (`api/bulk_transfer.py`) keep carrying real, pre-existing
  codes from a client/contractor's own numbering scheme straight through unaltered, without this
  feature's own auto-numbering ever overwriting a legitimately-supplied value. A code assigned
  this way is final: there is no further path, anywhere, that lets it be edited back to something
  else — matching the "no override" decision this app made deliberately.

Because this uses the real `Series` table, a System Manager can view and, if genuinely necessary,
correct any of these counters from Frappe's own **Document Naming Settings** page — its `prefix`
field autocompletes from every row currently in `tabSeries` (`get_transactions_and_prefixes()` /
`_evaluate_and_clean_templates()`, frappe/core/doctype/document_naming_settings/
document_naming_settings.py), not only prefixes declared via a doctype's own `naming_series`
field — so these dynamically-generated per-project/per-discipline/per-type keys show up there
exactly like a native naming series would. Keys are joined with "/", one of the few characters
`NamingSeries`'s own validation (`NAMING_SERIES_PATTERN` in frappe/model/naming.py) allows
alongside word characters, "-", ".", "#", "{" and "}" — "-" alone was deliberately avoided since a
discipline code or type abbreviation could itself contain one, which would make two distinct
(project, discipline) scopes collide onto the same joined key. The counter KEY (built from the
full discipline value, e.g. "ARCH") is independent of the DISPLAYED code's discipline segment
(a single letter, e.g. "A") — see `_discipline_letter` below — so a display-format change here
never risks colliding two previously-distinct counters onto one key.

Document/Submittal codes carry one more segment than Activity codes: a project-specific prefix,
matching the real client MDR (Master Document Register) convention this was built to follow —
e.g. `26010049-MSF-A-014` for a Siemens/Aseer PET-CT document. That prefix is never a stored
field (`custom_egc_project_code` was deliberately dropped as a second, disconnected identity
field alongside Project's own naming series) — it's detected from whatever real document/
submittal numbers the project already has (see `_project_prefix`). A brand-new project with no
numbered records yet falls back to its own Project ID; a System Manager can always override by
typing the desired first number manually (the "only fills if blank" contract), and every later
number on that project will detect and continue that same prefix.
"""

import re

import frappe
from frappe.utils import cint

from egc_projects.egc_projects import validators

CODE_DIGITS = 3

# {prefix}-{TYPE}-{DISC}-{seq} — prefix/TYPE/DISC are `.+`/`[A-Z0-9]+`/`[A-Z]` by construction
# (see _project_prefix/_discipline_letter), anchored so a prefix containing "-" or digits (e.g.
# "26010049") is still parsed correctly.
_CODE_PATTERN = re.compile(r"^(?P<prefix>.+)-(?P<type>[A-Z0-9]+)-(?P<disc>[A-Z])-(?P<seq>\d+)$")


def _discipline_letter(discipline: str) -> str:
	return (discipline or "")[:1].upper()


def _project_prefix(project: str) -> str:
	"""The numbering prefix this project's own Document/Submittal numbers already use, recovered
	from whichever existing number happens to match the pattern first (every number on one
	project shares one prefix by construction). Falls back to the Project's own ID for a project
	with no numbered records yet — never a stored field (see module docstring)."""
	for doctype, field in (("EGC Project Document", "document_number"), ("EGC Submittal", "submittal_number")):
		for value in frappe.get_all(doctype, filters={"project": project}, pluck=field, order_by="creation asc"):
			match = _CODE_PATTERN.match(value or "")
			if match:
				return match.group("prefix")
	return project


def _activity_series_key(project: str, discipline: str) -> str:
	return f"egc-activity-code/{project}/{discipline}"


def _document_series_key(project: str, discipline: str, type_abbr: str) -> str:
	return f"egc-document-code/{project}/{discipline}/{type_abbr}"


def _submittal_series_key(project: str, discipline: str, type_abbr: str) -> str:
	return f"egc-submittal-code/{project}/{discipline}/{type_abbr}"


def _peek_next(key: str) -> int:
	"""What `getseries(key, ...)` would hand out NEXT — a plain, lock-free read. There is no
	separate "peek without incrementing" helper in core; `getseries` itself always mutates, so a
	preview has to bypass it entirely. `Series.current` has no row at all for a brand-new key,
	and `cint(None) == 0`, so "next" is uniformly `current + 1` whether the row exists yet or
	not — matching `getseries`'s own "INSERT ... VALUES (1)" behavior for a first-ever call.

	Deliberately not `frappe.db.get_value("Series", key, "current")`: that helper defaults to
	`ORDER BY creation DESC`, but `tabSeries` is an internal bookkeeping table with no standard
	Frappe fields at all (no `creation`, no `modified`, ...) — the same reason core's own
	`getseries()` goes through `frappe.qb` directly instead."""
	series = frappe.qb.DocType("Series")
	current = frappe.qb.from_(series).where(series.name == key).select(series.current).run()
	return cint(current[0][0]) + 1 if current else 1


def _assign_next(key: str) -> str:
	from frappe.model.naming import getseries

	return getseries(key, CODE_DIGITS)


# --- Activity --------------------------------------------------------------------------------


@frappe.whitelist()
def suggest_activity_code(project: str | None = None, discipline: str | None = None) -> str:
	if not project or not discipline:
		return ""
	validators.require_project_permission(project)
	seq = _peek_next(_activity_series_key(project, discipline))
	return f"{discipline}-{seq:0{CODE_DIGITS}d}"


def assign_activity_code(project: str | None, discipline: str | None) -> str | None:
	if not (project and discipline):
		return None
	seq = _assign_next(_activity_series_key(project, discipline))
	return f"{discipline}-{seq}"


# --- Document --------------------------------------------------------------------------------


@frappe.whitelist()
def suggest_document_code(
	project: str | None = None, discipline: str | None = None, document_type: str | None = None
) -> str:
	if not project or not discipline or not document_type:
		return ""
	validators.require_project_permission(project)
	abbr = frappe.db.get_value("EGC Document Type", document_type, "abbreviation")
	if not abbr:
		return ""
	seq = _peek_next(_document_series_key(project, discipline, abbr))
	return f"{_project_prefix(project)}-{abbr}-{_discipline_letter(discipline)}-{seq:0{CODE_DIGITS}d}"


def assign_document_code(project: str | None, discipline: str | None, document_type: str | None) -> str | None:
	if not (project and discipline and document_type):
		return None
	abbr = frappe.db.get_value("EGC Document Type", document_type, "abbreviation")
	if not abbr:
		return None
	seq = _assign_next(_document_series_key(project, discipline, abbr))
	return f"{_project_prefix(project)}-{abbr}-{_discipline_letter(discipline)}-{seq}"


# --- Submittal -------------------------------------------------------------------------------


@frappe.whitelist()
def suggest_submittal_code(
	project: str | None = None, discipline: str | None = None, submittal_type: str | None = None
) -> str:
	if not project or not discipline or not submittal_type:
		return ""
	validators.require_project_permission(project)
	abbr = frappe.db.get_value("EGC Submittal Type", submittal_type, "abbreviation")
	if not abbr:
		return ""
	seq = _peek_next(_submittal_series_key(project, discipline, abbr))
	return f"{_project_prefix(project)}-{abbr}-{_discipline_letter(discipline)}-{seq:0{CODE_DIGITS}d}"


def assign_submittal_code(project: str | None, discipline: str | None, submittal_type: str | None) -> str | None:
	if not (project and discipline and submittal_type):
		return None
	abbr = frappe.db.get_value("EGC Submittal Type", submittal_type, "abbreviation")
	if not abbr:
		return None
	seq = _assign_next(_submittal_series_key(project, discipline, abbr))
	return f"{_project_prefix(project)}-{abbr}-{_discipline_letter(discipline)}-{seq}"
