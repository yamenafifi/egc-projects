"""Project Information domain helpers (ARCHITECTURE_V2.md §1/§2; Level 0 §8).

Project Information lives directly on the core `Project` doctype as Custom Fields (see
`project_custom_fields.py`). `custom_egc_stakeholders` is a Table field on `Project`, so its rows
carry `parenttype="Project"`.

Editing used to be routed entirely to the native `Project` form (no save endpoint existed here at
all). Level 0 §8 reverses that: "Do not force routine Project setup through the raw ERPNext
Project form" — routine Project Information maintenance now happens from the Hub itself, through
the whitelisted save/add/remove functions below. The native form still works (nothing here makes
it read-only), it's just no longer the primary path.

`resolve_role_user` and `get_stakeholders` are a binding contract: the Submittal Workflow engine
resolves a workflow step's `reviewer_role` through `resolve_role_user()`, so neither signature
may change. Both degrade gracefully to `None`/`[]` when a project has no stakeholders yet — that
is a normal state, not an error.
"""

from __future__ import annotations

import frappe

from egc_projects.egc_projects import validators

#: Roles surfaced in the Hub header's `profile.key_stakeholders` (ARCHITECTURE_V2.md §4).
#: Names match the seed list documented in ARCHITECTURE_V2.md §2 — kept here, not in
#: `constants.py` (lead-owned), since this is Project Information's own read-side concern.
KEY_STAKEHOLDER_ROLES = ("EGC Project Manager", "EGC Site Manager", "Client", "Consultant", "OEM")

#: External name -> the actual `custom_egc_*` fieldname on `Project`. Keeps the Hub-facing
#: contract stable and free of Frappe's custom-field naming convention, and is the one place
#: that would need editing if a field were ever renamed on `Project` itself. Shared by
#: `api/hub.py`'s `get_project_info` (read) and `save_project_profile` below (write).
PROFILE_FIELD_MAP = {
	"project_code": "custom_egc_project_code",
	"project_stage": "custom_egc_project_stage",
	"sector": "custom_egc_sector",
	"delivery_method": "custom_egc_delivery_method",
	"contract_type": "custom_egc_contract_type",
	"project_description": "custom_egc_project_description",
	"project_image": "custom_egc_project_image",
	"country": "custom_egc_country",
	"region": "custom_egc_region",
	"city": "custom_egc_city",
	"address": "custom_egc_address",
	"time_zone": "custom_egc_time_zone",
	"site_contact_name": "custom_egc_site_contact_name",
	"site_contact_phone": "custom_egc_site_contact_phone",
	"site_contact_email": "custom_egc_site_contact_email",
	"contract_date": "custom_egc_contract_date",
	"forecast_completion_date": "custom_egc_forecast_completion_date",
	"warranty_start_date": "custom_egc_warranty_start_date",
	"dlp_end_date": "custom_egc_dlp_end_date",
}

STAKEHOLDER_ROW_FIELDS = ("role", "person", "party_name", "organization", "user", "contact", "email", "phone", "is_primary")
EQUIPMENT_ROW_FIELDS = (
	"facility",
	"department",
	"modality",
	"wbs_node",
	"equipment_manufacturer",
	"equipment_model",
	"oem_reference",
	"equipment_delivery_target",
	"room_ready_target",
	"oem_installation_target",
	"commissioning_target",
	"notes",
)


def _require_profile_edit_access(project: str) -> None:
	validators.require_project_permission(project, "write")


@frappe.whitelist()
def save_project_profile(project: str, values: dict | str) -> None:
	"""Saves the SCALAR Project Information fields (Classification/Description/Address/Site
	Contact/Contract Dates) — `PROFILE_FIELD_MAP`'s fields. Stakeholders and Healthcare/Equipment
	rows are list data, handled by the add/remove endpoints below instead, not by this call."""
	_require_profile_edit_access(project)
	if isinstance(values, str):
		values = frappe.parse_json(values)

	doc = frappe.get_doc("Project", project)
	for external, internal in PROFILE_FIELD_MAP.items():
		if external in values:
			doc.set(internal, values[external])
	doc.save()


@frappe.whitelist()
def add_stakeholder(project: str, values: dict | str) -> str:
	_require_profile_edit_access(project)
	if isinstance(values, str):
		values = frappe.parse_json(values)

	row_values = {k: v for k, v in values.items() if k in STAKEHOLDER_ROW_FIELDS}
	# `EGCProjectStakeholder.fetch_from_person()` also does this, but only from `validate()` —
	# too late here: `Document._validate()` runs `_validate_mandatory()` (party_name is reqd)
	# BEFORE it runs the `validate` doc_event that would have filled it in. Resolving it here
	# means a person-only row (the normal path) never trips that ordering. A blank string counts
	# as "not provided" here, not just an absent key — a dialog submits every field it declared,
	# empty ones included.
	if row_values.get("person"):
		person = frappe.db.get_value(
			"EGC Person", row_values["person"], ["full_name", "organization", "user", "email", "phone"], as_dict=True
		)
		if person:
			row_values["party_name"] = row_values.get("party_name") or person.full_name
			row_values["organization"] = row_values.get("organization") or person.organization
			row_values["user"] = row_values.get("user") or person.user
			row_values["email"] = row_values.get("email") or person.email
			row_values["phone"] = row_values.get("phone") or person.phone

	doc = frappe.get_doc("Project", project)
	row = doc.append("custom_egc_stakeholders", row_values)
	doc.save()
	return row.name


@frappe.whitelist()
def remove_stakeholder(project: str, row_name: str) -> None:
	_require_profile_edit_access(project)
	doc = frappe.get_doc("Project", project)
	doc.custom_egc_stakeholders = [row for row in doc.custom_egc_stakeholders if row.name != row_name]
	doc.save()


@frappe.whitelist()
def add_equipment_item(project: str, values: dict | str) -> str:
	_require_profile_edit_access(project)
	if isinstance(values, str):
		values = frappe.parse_json(values)

	doc = frappe.get_doc("Project", project)
	row = doc.append("custom_egc_equipment_items", {k: v for k, v in values.items() if k in EQUIPMENT_ROW_FIELDS})
	doc.save()
	return row.name


@frappe.whitelist()
def remove_equipment_item(project: str, row_name: str) -> None:
	_require_profile_edit_access(project)
	doc = frappe.get_doc("Project", project)
	doc.custom_egc_equipment_items = [row for row in doc.custom_egc_equipment_items if row.name != row_name]
	doc.save()


def resolve_role_user(project: str, role_name: str) -> str | None:
	"""The `user` of the project's stakeholder row for `role_name`, or None.

	None covers two distinct cases uniformly, by design: the role isn't represented among this
	project's stakeholders, or it is but the stakeholder is a pure external party with no Frappe
	login (ARCHITECTURE_V2.md §2). A caller that needs to tell these apart should use
	`get_stakeholders` directly.
	"""
	if not project or not role_name:
		return None

	rows = frappe.get_all(
		"EGC Project Stakeholder",
		filters={"parent": project, "parenttype": "Project", "role": role_name},
		fields=["user"],
		order_by="is_primary desc, idx asc",
		limit=1,
	)
	return rows[0].user or None if rows else None


def get_stakeholders(project: str) -> list[dict]:
	"""Every stakeholder row for `project`, or `[]` if it has none yet."""
	if not project:
		return []

	return frappe.get_all(
		"EGC Project Stakeholder",
		filters={"parent": project, "parenttype": "Project"},
		fields=["name", *STAKEHOLDER_ROW_FIELDS],
		order_by="idx asc",
	)
