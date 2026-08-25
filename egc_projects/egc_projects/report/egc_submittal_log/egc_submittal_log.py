# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Log of submittals for a project (see docs/ARCHITECTURE.md §7). Overdue is derived exactly as
`api/hub.py` derives it: `current_due_date < today` while the submittal is still `Submitted` or
`Under Review` — never stored, so this and the Hub can never drift apart.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, sbool, today

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import validators


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validators.require_project_permission(filters.get("project"))

	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "submittal_number", "label": _("Submittal No"), "fieldtype": "Data", "width": 140},
		{"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 200},
		{
			"fieldname": "submittal_type",
			"label": _("Type"),
			"fieldtype": "Link",
			"options": "EGC Submittal Type",
			"width": 130,
		},
		{
			"fieldname": "discipline",
			"label": _("Discipline"),
			"fieldtype": "Link",
			"options": "EGC Discipline",
			"width": 110,
		},
		{"fieldname": "current_submission_label", "label": _("Current Submission"), "fieldtype": "Data", "width": 130},
		{"fieldname": "submittal_status", "label": _("Status"), "fieldtype": "Data", "width": 150},
		{"fieldname": "current_due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "days_overdue", "label": _("Days Overdue"), "fieldtype": "Int", "width": 100},
		{"fieldname": "last_response_date", "label": _("Last Response"), "fieldtype": "Date", "width": 110},
	]


def get_data(filters):
	query_filters = {"project": filters.project}
	if filters.get("submittal_type"):
		query_filters["submittal_type"] = filters.submittal_type
	if filters.get("discipline"):
		query_filters["discipline"] = filters.discipline
	if filters.get("status"):
		query_filters["submittal_status"] = filters.status

	rows = frappe.get_all(
		"EGC Submittal",
		filters=query_filters,
		fields=[
			"submittal_number",
			"title",
			"submittal_type",
			"discipline",
			"current_submission_label",
			"submittal_status",
			"current_due_date",
			"last_response_date",
		],
		order_by="submittal_number asc",
	)

	current_today = getdate(today())
	only_overdue = sbool(filters.get("overdue_only"))
	filtered = []
	for row in rows:
		is_overdue = bool(
			row.current_due_date
			and getdate(row.current_due_date) < current_today
			and row.submittal_status in c.SUBMISSION_OPEN_STATUSES
		)
		row["days_overdue"] = date_diff(today(), row.current_due_date) if is_overdue else 0
		if only_overdue and not is_overdue:
			continue
		filtered.append(row)
	return filtered
