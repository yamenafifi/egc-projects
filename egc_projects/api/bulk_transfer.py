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


# --- export / template -----------------------------------------------------------------------


@frappe.whitelist()
def get_export_template(project: str, doctype: str, file_type: str = "Excel", with_data: bool = True) -> None:
	"""Downloads a template for `doctype`, scoped to `project` — the SAME file whether the caller
	wants a blank template to fill in or the project's current rows to review/edit and re-import.

	Sets `frappe.response` directly and returns nothing: a real file download, via Frappe's own
	hidden-form-POST convention (matching every Data Export/Import endpoint in core) — the caller
	must POST to this method the same way `open_url_post` does, never through the usual
	`frappe.call()`-based `*_api.js` wrapper, which would just receive this as an inert response.
	"""
	_assert_allowed(doctype)
	validators.require_project_permission(project, "read")
	frappe.has_permission(doctype, "read", throw=True)

	from frappe.core.doctype.data_import.data_import import download_template

	download_template(
		doctype=doctype,
		export_records="by_filter" if cint(with_data) else "blank_template",
		export_filters=frappe.as_json({"project": project}),
		file_type=file_type,
	)


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
