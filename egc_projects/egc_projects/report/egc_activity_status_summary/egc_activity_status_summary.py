# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Activity register rendered in tree order (see docs/ARCHITECTURE.md §7).

Rows come back ordered by `lft` and carry an `indent` derived from each row's depth, which is
what makes Frappe's datatable draw the hierarchy instead of a flat list. Overdue is computed
here from the same helper the Activity controller uses — it is never a stored column.
"""

from __future__ import annotations

import frappe
from frappe import _

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import validators
from egc_projects.egc_projects.doctype.egc_activity.egc_activity import is_overdue

_FIELDS = (
	"name",
	"activity_code",
	"activity_name",
	"parent_egc_activity",
	"is_group",
	"lft",
	"wbs_node",
	"discipline",
	"planned_start_date",
	"planned_end_date",
	"status",
	"percent_complete",
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validators.require_project_permission(filters.get("project"))

	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "activity_code", "label": _("Activity Code"), "fieldtype": "Data", "width": 160},
		{"fieldname": "activity_name", "label": _("Activity"), "fieldtype": "Data", "width": 260},
		{
			"fieldname": "name",
			"label": _("Record"),
			"fieldtype": "Link",
			"options": "EGC Activity",
			"width": 200,
		},
		{
			"fieldname": "wbs_node",
			"label": _("WBS"),
			"fieldtype": "Link",
			"options": "EGC WBS Node",
			"width": 170,
		},
		{
			"fieldname": "discipline",
			"label": _("Discipline"),
			"fieldtype": "Link",
			"options": "EGC Discipline",
			"width": 110,
		},
		{"fieldname": "planned_start_date", "label": _("Planned Start"), "fieldtype": "Date", "width": 110},
		{"fieldname": "planned_end_date", "label": _("Planned Finish"), "fieldtype": "Date", "width": 110},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "percent_complete", "label": _("% Complete"), "fieldtype": "Percent", "width": 100},
		{"fieldname": "is_overdue", "label": _("Overdue"), "fieldtype": "Check", "width": 80},
	]


def get_data(filters):
	query_filters = {"project": filters.project}
	for fieldname in ("wbs_node", "discipline", "status"):
		if filters.get(fieldname):
			query_filters[fieldname] = filters.get(fieldname)

	rows = frappe.get_all("EGC Activity", filters=query_filters, fields=list(_FIELDS), order_by="lft asc")

	# Depth is derived from the parent chain rather than a stored level, so an activity moved in
	# the tree indents correctly without a backfill. When a filter excludes an ancestor, the
	# surviving descendant falls back to depth 0 instead of indenting under a row that is not
	# in the result set.
	depth_by_name: dict[str, int] = {}
	for row in rows:
		parent = row.parent_egc_activity
		row.indent = depth_by_name.get(parent, -1) + 1 if parent in depth_by_name else 0
		depth_by_name[row.name] = row.indent
		row.is_overdue = 1 if is_overdue(row.status, row.planned_end_date) else 0

	return rows


def get_status_filter_options() -> str:
	return "\n".join(("", *c.ACTIVITY_STATUSES))
