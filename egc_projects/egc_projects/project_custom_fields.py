"""Project Information, as Custom Fields on the core `Project` doctype (ARCHITECTURE_V2.md §1).

Custom fields, not a separate `EGC Project Profile` doctype and not a Hub-side form to fill
out — this data is edited on the native `Project` form, the same way `egc_hr` already extends
`Project` with its own `custom_egc_supervisors`/Project Location fields (see
`egc_hr.setup.bootstrap_custom_fields`, whose own comment there documents the pre-existing
`custom_latitude`/`custom_longitude`/`custom_geofence_radius`/`custom_site_coordinates_dms`/
`custom_project_location` fields on this site). This module is deliberately silent about site
GPS/geofencing and Supervisors — both already exist on `Project`, owned by that domain, and are
never duplicated here.

    bench --site dev.localhost execute egc_projects.egc_projects.project_custom_fields.run
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from egc_projects.egc_projects import validators

#: `insert_after: notes` places the whole tab right before the core "Connections" tab, after
#: every existing tab (Details/Costing/Progress/More Info) — appended, not interleaved with
#: core or egc_hr fields, so neither this app nor egc_hr can ever destabilise the other's
#: field positions by changing its own.
CUSTOM_FIELDS = {
	"Project": [
		{
			"fieldname": "custom_egc_project_info_tab",
			"label": "EGC Project Info",
			"fieldtype": "Tab Break",
			"insert_after": "notes",
		},
		{
			"fieldname": "custom_egc_classification_section",
			"label": "Classification",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_project_info_tab",
		},
		{
			"fieldname": "custom_egc_project_code",
			"label": "Project Code",
			"fieldtype": "Data",
			"insert_after": "custom_egc_classification_section",
		},
		{
			"fieldname": "custom_egc_project_stage",
			"label": "Project Stage",
			"fieldtype": "Select",
			# Leading blank line: an untouched Select must stay unset, never silently default to
			# the first option (frappe/model/create_new.py's `get_new_doc()` rule).
			"options": "\nDesign\nProcurement\nConstruction\nCommissioning\nCloseout\nWarranty",
			"insert_after": "custom_egc_project_code",
		},
		{
			"fieldname": "custom_egc_classification_col",
			"fieldtype": "Column Break",
			"insert_after": "custom_egc_project_stage",
		},
		{
			"fieldname": "custom_egc_sector",
			"label": "Sector",
			"fieldtype": "Select",
			"options": "\nHealthcare\nIndustrial\nCommercial\nInfrastructure\nOther",
			"insert_after": "custom_egc_classification_col",
		},
		{
			"fieldname": "custom_egc_delivery_method",
			"label": "Delivery Method",
			"fieldtype": "Select",
			"options": "\nDesign-Bid-Build\nDesign-Build\nEPC\nTurnkey\nOther",
			"insert_after": "custom_egc_sector",
		},
		{
			"fieldname": "custom_egc_contract_type",
			"label": "Contract Type",
			"fieldtype": "Select",
			"options": "\nLump Sum\nUnit Price\nCost Plus\nTime & Material\nOther",
			"insert_after": "custom_egc_delivery_method",
		},
		{
			"fieldname": "custom_egc_project_description",
			"label": "Project Description",
			"fieldtype": "Small Text",
			"insert_after": "custom_egc_contract_type",
		},
		{
			"fieldname": "custom_egc_work_scope",
			"label": "Work Scope",
			"fieldtype": "Text Editor",
			"insert_after": "custom_egc_project_description",
		},
		{
			"fieldname": "custom_egc_commercial_section",
			"label": "Commercial",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_work_scope",
		},
		{
			"fieldname": "custom_egc_contract_value",
			"label": "Contract Value",
			"fieldtype": "Currency",
			"insert_after": "custom_egc_commercial_section",
		},
		{
			"fieldname": "custom_egc_commercial_col",
			"fieldtype": "Column Break",
			"insert_after": "custom_egc_contract_value",
		},
		{
			"fieldname": "custom_egc_project_image",
			"label": "Project Image",
			"fieldtype": "Attach Image",
			"insert_after": "custom_egc_commercial_col",
		},
		{
			"fieldname": "custom_egc_stakeholders_section",
			"label": "Stakeholders",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_project_image",
			"description": (
				"External and internal parties on this project (Client, Consultant, Main "
				"Contractor, OEM, EGC roles, ...) — a distinct concern from egc_hr's own "
				"Supervisors table above, which governs attendance approval only."
			),
		},
		{
			"fieldname": "custom_egc_stakeholders",
			"fieldtype": "Table",
			"options": "EGC Project Stakeholder",
			"insert_after": "custom_egc_stakeholders_section",
		},
		{
			"fieldname": "custom_egc_address_section",
			"label": "Address",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_stakeholders",
			"description": (
				"Postal/administrative address — GPS coordinates and geofencing live in the "
				"Project Location section above (egc_hr), not duplicated here."
			),
		},
		{
			"fieldname": "custom_egc_country",
			"label": "Country",
			"fieldtype": "Link",
			"options": "Country",
			"insert_after": "custom_egc_address_section",
		},
		{
			"fieldname": "custom_egc_region",
			"label": "Region",
			"fieldtype": "Data",
			"insert_after": "custom_egc_country",
		},
		{
			"fieldname": "custom_egc_city",
			"label": "City",
			"fieldtype": "Data",
			"insert_after": "custom_egc_region",
		},
		{
			"fieldname": "custom_egc_address_col",
			"fieldtype": "Column Break",
			"insert_after": "custom_egc_city",
		},
		{
			"fieldname": "custom_egc_address",
			"label": "Address",
			"fieldtype": "Small Text",
			"insert_after": "custom_egc_address_col",
		},
		{
			"fieldname": "custom_egc_time_zone",
			"label": "Time Zone",
			"fieldtype": "Data",
			"insert_after": "custom_egc_address",
		},
		{
			"fieldname": "custom_egc_site_contact_section",
			"label": "Site Contact",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_time_zone",
		},
		{
			"fieldname": "custom_egc_site_contact_name",
			"label": "Site Contact Name",
			"fieldtype": "Data",
			"insert_after": "custom_egc_site_contact_section",
		},
		{
			"fieldname": "custom_egc_site_contact_col",
			"fieldtype": "Column Break",
			"insert_after": "custom_egc_site_contact_name",
		},
		{
			"fieldname": "custom_egc_site_contact_phone",
			"label": "Site Contact Phone",
			"fieldtype": "Data",
			"options": "Phone",
			"insert_after": "custom_egc_site_contact_col",
		},
		{
			"fieldname": "custom_egc_site_contact_email",
			"label": "Site Contact Email",
			"fieldtype": "Data",
			"options": "Email",
			"insert_after": "custom_egc_site_contact_phone",
		},
		{
			"fieldname": "custom_egc_contract_dates_section",
			"label": "Contract Dates",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_site_contact_email",
		},
		{
			"fieldname": "custom_egc_contract_date",
			"label": "Contract Date",
			"fieldtype": "Date",
			"insert_after": "custom_egc_contract_dates_section",
		},
		{
			"fieldname": "custom_egc_forecast_completion_date",
			"label": "Forecast Completion Date",
			"fieldtype": "Date",
			"insert_after": "custom_egc_contract_date",
		},
		{
			"fieldname": "custom_egc_contract_dates_col",
			"fieldtype": "Column Break",
			"insert_after": "custom_egc_forecast_completion_date",
		},
		{
			"fieldname": "custom_egc_warranty_start_date",
			"label": "Warranty Start Date",
			"fieldtype": "Date",
			"insert_after": "custom_egc_contract_dates_col",
		},
		{
			"fieldname": "custom_egc_dlp_end_date",
			"label": "DLP End Date",
			"fieldtype": "Date",
			"insert_after": "custom_egc_warranty_start_date",
		},
		{
			"fieldname": "custom_egc_equipment_section",
			"label": "Healthcare / Equipment",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_dlp_end_date",
			"collapsible": 1,
		},
		{
			"fieldname": "custom_egc_equipment_items",
			"fieldtype": "Table",
			"options": "EGC Project Equipment Item",
			"insert_after": "custom_egc_equipment_section",
		},
	]
}


def create() -> None:
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)


def run() -> None:
	create()
	frappe.db.commit()
	print("EGC Project Info custom fields bootstrap complete.")


def validate_project(doc, method=None) -> None:
	"""Wired as a `Project` `validate` doc_event (hooks.py) — `Project` is core, so this can't
	live as a doctype-controller `validate()` the way it did on the old `EGC Project Profile`.
	Same check, same reason: a Healthcare/Equipment item's `wbs_node` must belong to this same
	project (docs/ARCHITECTURE_V2.md §3)."""
	for row in doc.get("custom_egc_equipment_items") or []:
		if not row.wbs_node:
			continue
		# `EGC Project Equipment Item` has no `project` field of its own — set it on the
		# in-memory row so the shared validator can anchor against this Project, per
		# ARCHITECTURE_V2.md §1 ("no new validation pattern invented").
		row.project = doc.name
		validators.validate_same_project(row, "wbs_node", "EGC WBS Node", _("WBS Node"))
