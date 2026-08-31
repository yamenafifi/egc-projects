"""Export/Import for the Hub's own registers — WBS, Activities, Submittals, Documents (direct
user instruction: buttons inside the Project Hub itself, never a navigate-away to Frappe's own
`/app/data-export`/`/app/data-import` list views).

Reuses Frappe's own Data Export/Data Import machinery end to end — never a hand-rolled CSV/XLSX
parser — so an imported row goes through the exact same `frappe.get_doc(...).insert()`/`.save()`
path a hand-created record does, and every doctype's own `validate()`
(`document_control.py`/`activity_control.py`'s "one writer" rules, `validators.validate_tree_parent`,
...) still fires per row exactly as it would for a record a person typed in by hand. The one thing
Frappe's own tool has no concept of at all — "this import belongs to exactly one Project" — is
enforced here: `enforce_bulk_import_project` (wired in hooks.py as an extra `validate` handler on
all four doctypes) forces every new row's `project` field to the project the import was opened
from, and rejects outright any row that would touch an EXISTING record belonging to a different
project, so a crafted spreadsheet can never inject or reassign data across a project boundary —
something no amount of DocType-level `import` permission alone would prevent.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from egc_projects.egc_projects import validators

#: Every doctype this Hub feature covers — each carries a direct `project` Link field (unlike a
#: child record such as a Document Revision, which is scoped through its parent instead, and
#: isn't a sensible target for a flat spreadsheet import in the first place).
ALLOWED_TRANSFER_DOCTYPES = (
	"EGC WBS Node",
	"EGC Activity",
	"EGC Submittal",
	"EGC Project Document",
)

#: `frappe.flags` key `enforce_bulk_import_project` checks — set only for the duration of
#: `import_records()`'s own call to Frappe's Importer, always cleared in a `finally`.
BULK_IMPORT_PROJECT_FLAG = "egc_bulk_import_project"


def _assert_allowed(doctype: str) -> None:
	if doctype not in ALLOWED_TRANSFER_DOCTYPES:
		frappe.throw(
			_("{0} does not support Export/Import from the Hub.").format(doctype),
			exc=frappe.ValidationError,
		)


def _all_export_fields(doctype: str) -> dict:
	"""Every field on `doctype`, in the shape `Exporter` expects — the same `{doctype: [...]}`
	map Frappe's own "Download Template" dialog builds from its "Select All" MultiCheck. Skipped
	when calling `download_template` directly (not through that dialog): `Exporter.__init__`
	unconditionally does `self.export_fields.items()`, so a missing/None `export_fields` is a hard
	crash, not a "default to everything." None of this Hub's 4 export-enabled doctypes has a
	Table field of its own, so a flat field list for just `doctype` is enough — Exporter's own
	`get_exportable_fields` already drops anything non-exportable (Section Break, etc.)."""
	meta = frappe.get_meta(doctype)
	return {doctype: ["name", *(df.fieldname for df in meta.fields)]}


# --- export / template -----------------------------------------------------------------------


@frappe.whitelist()
def get_export_template(
	project: str,
	doctype: str,
	file_type: str = "Excel",
	with_data: bool = True,
	names: list[str] | str | None = None,
) -> None:
	"""Downloads a template for `doctype`, scoped to `project` — the SAME file whether the caller
	wants a blank template to fill in, the project's current rows to review/edit and re-import, or
	(when `names` is given, from the Hub's own row-checkbox selection) just those specific rows.

	Sets `frappe.response` directly and returns nothing: a real file download, via Frappe's own
	hidden-form-POST convention (matching every Data Export/Import endpoint in core) — the caller
	must POST to this method the same way `open_url_post` does, never through the usual
	`frappe.call()`-based `*_api.js` wrapper, which would just receive this as an inert response.
	"""
	_assert_allowed(doctype)
	validators.require_project_permission(project, "read")
	frappe.has_permission(doctype, "read", throw=True)

	from frappe.core.doctype.data_import.data_import import download_template

	names = frappe.parse_json(names) if isinstance(names, str) else names
	# `project` stays in the filter even for an explicit selection — a selection is always read
	# off THIS project's own already-scoped table, but this keeps that invariant true regardless
	# of how `names` was produced, the same "never trust the caller alone" discipline every other
	# project-scoped filter in this module already follows.
	export_filters = {"project": project, "name": ["in", names]} if names else {"project": project}

	download_template(
		doctype=doctype,
		export_fields=_all_export_fields(doctype),
		export_records="by_filter" if (names or cint(with_data)) else "blank_template",
		export_filters=frappe.as_json(export_filters),
		file_type=file_type,
	)


@frappe.whitelist()
def delete_records(project: str, doctype: str, names: list[str] | str) -> dict:
	"""Bulk-deletes specific `doctype` rows — the Hub's own checkbox-select "Actions > Delete",
	matching the Frappe List View's own select-all-then-bulk-delete convention. Each name is
	verified to actually belong to `project` before deletion (same discipline as
	`enforce_bulk_import_project`'s cross-project check on import): a crafted name list is never
	trusted to already be scoped to the right project just because the UI it came from was.
	"""
	_assert_allowed(doctype)
	validators.require_project_permission(project, "write")
	frappe.has_permission(doctype, "delete", throw=True)

	names = frappe.parse_json(names) if isinstance(names, str) else names
	if not names:
		frappe.throw(_("No records selected."), exc=frappe.ValidationError)

	owned_names = set(
		frappe.get_all(doctype, filters={"project": project, "name": ["in", names]}, pluck="name")
	)

	deleted, failures = [], []
	for name in names:
		if name not in owned_names:
			failures.append({"name": name, "exception": _("Does not belong to this project.")})
			continue
		try:
			frappe.delete_doc(doctype, name, ignore_permissions=True)
			deleted.append(name)
		except Exception as e:
			failures.append({"name": name, "exception": str(e)})

	return {"deleted_count": len(deleted), "failure_count": len(failures), "failures": failures}


# --- import ------------------------------------------------------------------------------------


def enforce_bulk_import_project(doc, method=None) -> None:
	"""Extra `validate` handler (hooks.py) on every Export/Import-enabled doctype — a no-op
	outside of `import_records()`'s own controlled window. Inside it: a brand-new row is
	force-scoped to the project the import was opened from, regardless of whatever its own
	`project` column said or omitted; an EXISTING row is rejected outright if it already belongs
	to a different project — reassigning it would silently move real data across a project
	boundary, which is worse than simply refusing the row.
	"""
	forced_project = frappe.flags.get(BULK_IMPORT_PROJECT_FLAG)
	if not forced_project:
		return
	if doc.is_new():
		doc.project = forced_project
	elif doc.project != forced_project:
		frappe.throw(
			_("{0} belongs to a different project and cannot be touched by this import.").format(doc.name),
			title=_("Not Allowed"),
			exc=frappe.ValidationError,
		)


@frappe.whitelist()
def import_records(
	project: str,
	doctype: str,
	file_url: str,
	update_existing: bool = False,
	send_email: bool = False,
) -> dict:
	"""Bulk-creates/updates `doctype` rows from an uploaded file, through Frappe's own Importer.

	`send_email` maps straight onto Data Import's own `mute_emails` field, just framed the other
	way round — this app asks "do you want notifications", Frappe's own field asks "do you want
	them muted" (and defaults to muted for exactly the reason a bulk operation usually shouldn't
	spam a hundred ball-in-court emails at once).
	"""
	_assert_allowed(doctype)
	validators.require_project_permission(project, "write")
	frappe.has_permission(doctype, "create", throw=True)

	data_import = frappe.new_doc("Data Import")
	data_import.reference_doctype = doctype
	data_import.import_type = "Update Existing Records" if cint(update_existing) else "Insert New Records"
	data_import.import_file = file_url
	data_import.mute_emails = 0 if cint(send_email) else 1
	# Already permission-checked above (project-scoped, which Data Import's own generic
	# `frappe.has_permission(doctype, "import")` check knows nothing about) — ignore_permissions
	# here skips that redundant, coarser check, matching this app's own established pattern
	# (submittal_control.py's engine writes, api/directory.py's grant/revoke) of checking once,
	# explicitly, up front, rather than a second time on the internal write.
	data_import.insert(ignore_permissions=True)

	frappe.flags[BULK_IMPORT_PROJECT_FLAG] = project
	try:
		from frappe.core.doctype.data_import.importer import Importer

		Importer(doctype, data_import=data_import).import_data()
	finally:
		frappe.flags[BULK_IMPORT_PROJECT_FLAG] = None

	data_import.reload()
	log_rows = frappe.get_all(
		"Data Import Log",
		filters={"data_import": data_import.name},
		fields=["docname", "success", "exception", "row_indexes"],
		order_by="log_index asc",
	)
	return {
		"data_import": data_import.name,
		"status": data_import.status,
		"success_count": sum(1 for row in log_rows if row.success),
		"failure_count": sum(1 for row in log_rows if not row.success),
		"log": log_rows,
	}
