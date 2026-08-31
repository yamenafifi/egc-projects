"""Project Information, as Custom Fields on the core `Project` doctype (ARCHITECTURE_V2.md §1).

Custom fields, not a separate `EGC Project Profile` doctype and not a Hub-side form to fill
out — this data is edited on the native `Project` form, the same way `egc_hr` already extends
`Project` with its own `custom_egc_supervisors`/Project Location fields (see
`egc_hr.setup.bootstrap_custom_fields`, whose own comment there documents the pre-existing
`custom_latitude`/`custom_longitude`/`custom_geofence_radius`/`custom_site_coordinates_dms`/
`custom_project_location` fields on this site). This module is deliberately silent about site
GPS/geofencing and Supervisors — both already exist on `Project`, owned by that domain, and are
never duplicated here.

Distributed across the Project form's EXISTING tabs (no dedicated "EGC Project Info" tab):
Classification/Description/Contract Dates land at the end of the (implicit, un-tab-broken)
Details tab; Stakeholders/Address/Site Contact/Healthcare-Equipment land at the end of the native
More Info tab, after `notes`. Nothing is added to Costing — "Contract Value" used to live there as
a manually-entered field, but core's own `total_sales_amount` plus `EGC Change Order`
(api/change_orders.py) now cover that ground with a single source of truth (Original Scope +
Change Orders = Total), so a second, unsynced number would only contradict it.

**The bridging-anchor fields** (`custom_egc_details_bridge`/`custom_egc_more_info_bridge`, hidden,
otherwise inert) exist ONLY to work around a real quirk in `Meta.sort_fields()`
(frappe/model/meta.py): anchoring a Section Break's `insert_after` directly at a CORE field name
makes it walk FORWARD through the doctype's `field_order` looking for the next Section Break (or a
field of the same type as the anchor) — with no Tab Break stopping condition — and can land the
section past a tab boundary into the NEXT tab instead of at the end of the current one. Anchoring
at a CUSTOM field's name instead never triggers that walk at all (the walk only fires when
`insert_after in field_order`, and `field_order` — read from the doctype's own JSON — only ever
contains STANDARD fieldnames), so a plain, non-breaking custom field placed once at each risky
boundary makes every other field anchored to IT immune to the quirk. Confirmed directly against
`Meta.sort_fields()`'s source, not assumed.

    bench --site dev.localhost execute egc_projects.egc_projects.project_custom_fields.run
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from egc_projects.egc_projects import constants as c, validators

#: Custom Fields once used to build a dedicated "EGC Project Info" tab (Tab Break) with a
#: "Commercial" section (Contract Value) inside it — both superseded, per this module's own
#: docstring. `create_custom_fields` only creates/updates fields present in `CUSTOM_FIELDS`, so
#: these are deleted explicitly in `create()` below; anything not listed here keeps its fieldname
#: and data untouched, just repositioned.
_RETIRED_FIELDS = (
	"custom_egc_project_info_tab",
	"custom_egc_commercial_section",
	"custom_egc_commercial_col",
	"custom_egc_contract_value",
	# Work Scope (Text Editor) — dropped per explicit user feedback: scope is defined in
	# Activities and WBS, not a freeform rich-text field duplicating that.
	"custom_egc_work_scope",
	# The old flat address fields — superseded by `custom_project_address`, a plain Link to
	# core's own `Address` doctype (see below), so a project's address is one real address
	# record instead of five unstructured strings with no relationship to anything else in
	# ERPNext. Dropped outright, not migrated — dev-environment data only at the time this
	# changed.
	"custom_egc_address_section",
	"custom_egc_country",
	"custom_egc_region",
	"custom_egc_city",
	"custom_egc_address_col",
	"custom_egc_address",
	"custom_egc_time_zone",
	# Project Code — a separate, manually-typed field with no relationship to Project's own
	# `PROJ-.####` naming series, dropped per explicit user feedback (2026-08-30): the series
	# is the project's identity, a second manually-typed "code" alongside it only invites drift.
	"custom_egc_project_code",
	# Site Contact — three flat name/phone/email fields, dropped in favor of a normal Directory
	# entry (a Stakeholder row with the new "Site Contact" role — see install.py's
	# STAKEHOLDER_ROLES) per explicit user feedback: "the site contact should be a CRM linked
	# thing," not a fourth parallel identity mechanism alongside the Directory.
	"custom_egc_site_contact_section",
	"custom_egc_site_contact_name",
	"custom_egc_site_contact_col",
	"custom_egc_site_contact_phone",
	"custom_egc_site_contact_email",
)


def _select_options(values: tuple[str, ...]) -> str:
	"""Leading blank line: an untouched Select must stay unset, never silently default to the
	first option (frappe/model/create_new.py's `get_new_doc()` rule)."""
	return "\n" + "\n".join(values)


CUSTOM_FIELDS = {
	"Project": [
		# -- bridging anchors (see module docstring) --------------------------------------------
		{
			"fieldname": "custom_egc_details_bridge",
			"fieldtype": "Data",
			"insert_after": "actual_end_date",
			"hidden": 1,
			"read_only": 1,
			"print_hide": 1,
		},
		{
			"fieldname": "custom_egc_more_info_bridge",
			"fieldtype": "Data",
			"insert_after": "notes",
			"hidden": 1,
			"read_only": 1,
			"print_hide": 1,
		},
		# -- Details tab: Classification -----------------------------------------------------
		{
			"fieldname": "custom_egc_classification_section",
			"label": "Classification",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_details_bridge",
		},
		{
			"fieldname": "custom_egc_project_stage",
			"label": "Project Stage",
			"fieldtype": "Select",
			"options": _select_options(c.PROJECT_STAGES),
			"insert_after": "custom_egc_classification_section",
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
			"options": _select_options(c.SECTORS),
			"insert_after": "custom_egc_classification_col",
		},
		{
			"fieldname": "custom_egc_delivery_method",
			"label": "Delivery Method",
			"fieldtype": "Select",
			"options": _select_options(c.DELIVERY_METHODS),
			"insert_after": "custom_egc_sector",
		},
		{
			"fieldname": "custom_egc_contract_type",
			"label": "Contract Type",
			"fieldtype": "Select",
			"options": _select_options(c.CONTRACT_TYPES),
			"insert_after": "custom_egc_delivery_method",
		},
		# -- Details tab: Description ---------------------------------------------------------
		{
			"fieldname": "custom_egc_description_section",
			"label": "Description",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_contract_type",
		},
		{
			"fieldname": "custom_egc_project_description",
			"label": "Project Description",
			"fieldtype": "Small Text",
			"insert_after": "custom_egc_description_section",
		},
		{
			"fieldname": "custom_egc_description_col",
			"fieldtype": "Column Break",
			"insert_after": "custom_egc_project_description",
		},
		{
			"fieldname": "custom_egc_project_image",
			"label": "Project Image",
			"fieldtype": "Attach Image",
			"insert_after": "custom_egc_description_col",
		},
		# -- Details tab: Contract Dates --------------------------------------------------------
		{
			"fieldname": "custom_egc_contract_dates_section",
			"label": "Contract Dates",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_project_image",
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
		# -- More Info tab: Stakeholders ---------------------------------------------------------
		{
			"fieldname": "custom_egc_stakeholders_section",
			"label": "Stakeholders",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_more_info_bridge",
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
		# -- More Info tab: Address ------------------------------------------------------------
		# A single Link to core's own `Address` doctype rather than a bespoke set of
		# country/region/city/address/time-zone fields — one real address record (shared with
		# every other ERPNext doctype that has one), not five unstructured strings that only
		# ever existed here. `get_query`/auto-linking live in `project.js` +
		# `project_profile.get_addresses_for_project`/`ensure_address_linked_to_project` — GPS
		# coordinates and geofencing stay in the Project Location section above (egc_hr), not
		# duplicated here.
		{
			"fieldname": "custom_project_address_section",
			"label": "Address",
			"fieldtype": "Section Break",
			"insert_after": "custom_egc_stakeholders",
		},
		{
			"fieldname": "custom_project_address",
			"label": "Project Address",
			"fieldtype": "Link",
			"options": "Address",
			"insert_after": "custom_project_address_section",
		},
		# -- More Info tab: Healthcare / Equipment ----------------------------------------------
		{
			"fieldname": "custom_egc_equipment_section",
			"label": "Healthcare / Equipment",
			"fieldtype": "Section Break",
			"insert_after": "custom_project_address",
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
	for fieldname in _RETIRED_FIELDS:
		name = frappe.db.get_value("Custom Field", {"dt": "Project", "fieldname": fieldname})
		if name:
			frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


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

	# Frappe never dispatches a child table row's own `validate()` automatically on parent save
	# (confirmed directly against `Document._save()`/`update_children()` — they call `d.db_update()`
	# per row, never `run_method("validate")`) — every other child-row validation in this app
	# already works around this the same way (see the WBS Node check just above); `EGC Project
	# Stakeholder.fetch_from_person()` needs the identical explicit call, or a native-form edit
	# to `person`/`organization` on this table would silently never re-mirror.
	for row in doc.get("custom_egc_stakeholders") or []:
		row.fetch_from_person()
