"""The many-to-many relationship layer between `EGC Activity` and the records that apply to it.

`EGC Activity Link` is a standalone DocType, never a child table, precisely because a Submittal
or a Drawing (an `EGC Project Document`) can apply to many Activities and one Activity can carry
many links — a genuine many-to-many. `ALLOWED_LINK_DOCTYPES` is the single registry of what may
be linked; adding a future target (`EGC RFI`, `EGC MIR`, `EGC ITP`, ...) is a one-line change
here and needs no schema change and no numbered hard-coded link field anywhere (see
docs/ARCHITECTURE.md §2.6, §9).
"""

from __future__ import annotations

import frappe
from frappe import _

from egc_projects.egc_projects import constants as c

#: doctype -> {label, title_field, route}. `route` is the Desk form route slug
#: (`frappe.scrub` on the doctype name replaces spaces with dashes and lowercases), used by the
#: client renderer to deep-link a row without a round-trip.
ALLOWED_LINK_DOCTYPES: dict[str, dict] = {
	"EGC Project Document": {
		"label": "Project Document",
		"title_field": "title",
		"route": "egc-project-document",
	},
	"EGC Submittal": {
		"label": "Submittal",
		"title_field": "title",
		"route": "egc-submittal",
	},
}

#: Per-target-doctype extra fields fetched in one query per doctype by `get_links_for_activity`,
#: so a row renders its target's live status without a second round-trip per row.
_TARGET_STATUS_FIELDS: dict[str, tuple[str, ...]] = {
	"EGC Project Document": ("document_number", "current_revision_label", "approval_status", "discipline"),
	"EGC Submittal": (
		"submittal_number",
		"submittal_status",
		"current_submission_label",
		"submittal_type",
		"discipline",
		"ball_in_court",
		"current_due_date",
	),
}


def is_allowed(link_doctype: str) -> bool:
	return link_doctype in ALLOWED_LINK_DOCTYPES


def _get_target_status_map(link_doctype: str, names: list[str]) -> dict[str, dict]:
	"""One query for every target of `link_doctype` referenced by the current row set.

	Degrades to an empty map for a registered doctype whose table does not exist yet (e.g.
	`EGC Submittal` while that work package is still in progress) instead of raising.
	"""
	if not names or not frappe.db.table_exists(link_doctype):
		return {}

	extra_fields = _TARGET_STATUS_FIELDS.get(link_doctype, ())
	rows = frappe.get_all(
		link_doctype,
		filters={"name": ("in", names)},
		fields=["name", *extra_fields],
	)
	return {row.name: {field: row.get(field) for field in extra_fields} for row in rows}


@frappe.whitelist()
def get_links_for_activity(activity: str) -> list[dict]:
	"""Every link row for `activity`, each carrying its target's live display state.

	Fetches target status in one query per distinct `link_doctype` among the rows, not one
	query per row.
	"""
	if not activity:
		return []
	frappe.has_permission("EGC Activity", "read", doc=activity, throw=True)

	rows = frappe.get_all(
		"EGC Activity Link",
		filters={"activity": activity},
		fields=[
			"name",
			"link_doctype",
			"link_name",
			"link_title",
			"link_purpose",
			"is_blocking",
			"remarks",
			"creation",
			"owner",
		],
		order_by="creation asc",
	)
	if not rows:
		return []

	names_by_doctype: dict[str, list[str]] = {}
	for row in rows:
		names_by_doctype.setdefault(row.link_doctype, []).append(row.link_name)

	status_by_doctype = {
		link_doctype: _get_target_status_map(link_doctype, names)
		for link_doctype, names in names_by_doctype.items()
	}

	result = []
	for row in rows:
		row_dict = dict(row)
		row_dict.update(status_by_doctype.get(row.link_doctype, {}).get(row.link_name, {}))
		result.append(row_dict)
	return result


@frappe.whitelist()
def get_activities_for(link_doctype: str, link_name: str) -> list[dict]:
	"""Every Activity linked to `link_doctype`/`link_name` — the reverse direction."""
	if not link_doctype or not link_name:
		return []
	frappe.has_permission(link_doctype, "read", doc=link_name, throw=True)

	rows = frappe.get_all(
		"EGC Activity Link",
		filters={"link_doctype": link_doctype, "link_name": link_name},
		fields=["name", "activity", "link_purpose", "is_blocking", "remarks"],
		order_by="creation asc",
	)
	if not rows:
		return []

	activities = frappe.get_all(
		"EGC Activity",
		filters={"name": ("in", [row.activity for row in rows])},
		fields=["name", "activity_code", "activity_name", "status", "project"],
	)
	activity_by_name = {activity.name: activity for activity in activities}

	result = []
	for row in rows:
		activity = activity_by_name.get(row.activity)
		if not activity:
			# The activity link outlived its activity (should not happen; links are validated
			# against a live activity), so skip rather than render a broken row.
			continue
		result.append(
			{
				"name": row.name,
				"activity": row.activity,
				"activity_code": activity.activity_code,
				"activity_name": activity.activity_name,
				"status": activity.status,
				"project": activity.project,
				"link_purpose": row.link_purpose,
				"is_blocking": row.is_blocking,
				"remarks": row.remarks,
			}
		)
	return result


@frappe.whitelist()
def add_link(
	activity: str,
	link_doctype: str,
	link_name: str,
	link_purpose: str = c.LINK_PURPOSE_REFERENCE,
	remarks: str | None = None,
) -> str:
	if not is_allowed(link_doctype):
		frappe.throw(
			_("{0} is not a linkable record type. Allowed: {1}").format(
				frappe.bold(link_doctype or ""), ", ".join(ALLOWED_LINK_DOCTYPES.keys())
			),
			title=_("Not Allowed"),
			exc=frappe.ValidationError,
		)

	frappe.has_permission("EGC Activity", "write", doc=activity, throw=True)
	frappe.has_permission(link_doctype, "read", doc=link_name, throw=True)

	doc = frappe.get_doc(
		{
			"doctype": "EGC Activity Link",
			"activity": activity,
			"link_doctype": link_doctype,
			"link_name": link_name,
			"link_purpose": link_purpose or c.LINK_PURPOSE_REFERENCE,
			"remarks": remarks,
		}
	)
	doc.insert()
	return doc.name


@frappe.whitelist()
def remove_link(name: str) -> None:
	link = frappe.get_doc("EGC Activity Link", name)
	frappe.has_permission("EGC Activity", "write", doc=link.activity, throw=True)
	frappe.has_permission(link.link_doctype, "read", doc=link.link_name, throw=True)
	frappe.delete_doc("EGC Activity Link", name)
