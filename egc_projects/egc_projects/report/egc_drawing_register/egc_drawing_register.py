# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Register of controlled documents whose `document_type.is_drawing = 1` (see
docs/ARCHITECTURE.md §7). There is no separate Drawing DocType — this report is the only place
that filters `EGC Project Document` down to that subset for presentation.
"""

from __future__ import annotations

import frappe
from frappe import _

from egc_projects.api.hub import get_drawing_document_types
from egc_projects.egc_projects import validators


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validators.require_project_permission(filters.get("project"))

	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"fieldname": "document_number", "label": _("Drawing No"), "fieldtype": "Data", "width": 140},
		{"fieldname": "title", "label": _("Title"), "fieldtype": "Data", "width": 220},
		{
			"fieldname": "discipline",
			"label": _("Discipline"),
			"fieldtype": "Link",
			"options": "EGC Discipline",
			"width": 110,
		},
		{
			"fieldname": "drawing_set",
			"label": _("Set"),
			"fieldtype": "Link",
			"options": "EGC Drawing Set",
			"width": 120,
		},
		{
			"fieldname": "drawing_area",
			"label": _("Area"),
			"fieldtype": "Link",
			"options": "EGC Drawing Area",
			"width": 120,
		},
		{"fieldname": "current_revision_label", "label": _("Current Rev"), "fieldtype": "Data", "width": 100},
		{"fieldname": "approval_status", "label": _("Approval Status"), "fieldtype": "Data", "width": 160},
		{"fieldname": "current_revision_date", "label": _("Revision Date"), "fieldtype": "Date", "width": 110},
		{
			"fieldname": "document",
			"label": _("Document"),
			"fieldtype": "Link",
			"options": "EGC Project Document",
			"width": 160,
		},
	]


def get_data(filters):
	drawing_types = get_drawing_document_types()
	if not drawing_types:
		return []

	requested_type = filters.get("document_type")
	if requested_type:
		if requested_type not in drawing_types:
			return []
		document_type_filter = requested_type
	else:
		document_type_filter = ("in", drawing_types)

	query_filters = {"project": filters.project, "document_type": document_type_filter}
	if filters.get("discipline"):
		query_filters["discipline"] = filters.discipline
	if filters.get("approval_status"):
		query_filters["approval_status"] = filters.approval_status
	if filters.get("drawing_set"):
		query_filters["drawing_set"] = filters.drawing_set
	if filters.get("drawing_area"):
		query_filters["drawing_area"] = filters.drawing_area

	return frappe.get_all(
		"EGC Project Document",
		filters=query_filters,
		fields=[
			"name as document",
			"document_number",
			"title",
			"discipline",
			"drawing_set",
			"drawing_area",
			"current_revision_label",
			"approval_status",
			"current_revision_date",
		],
		order_by="document_number asc",
	)
