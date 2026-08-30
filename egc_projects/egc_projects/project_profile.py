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

from egc_projects.egc_projects import directory, validators

#: Roles surfaced in the Hub header's `profile.key_stakeholders` (ARCHITECTURE_V2.md §4).
#: Names match the seed list documented in ARCHITECTURE_V2.md §2 — kept here, not in
#: `constants.py` (lead-owned), since this is Project Information's own read-side concern.
KEY_STAKEHOLDER_ROLES = ("EGC Project Manager", "EGC Site Manager", "Client", "Consultant", "OEM")

#: External name -> the actual `custom_egc_*` fieldname on `Project`. Keeps the Hub-facing
#: contract stable and free of Frappe's custom-field naming convention, and is the one place
#: that would need editing if a field were ever renamed on `Project` itself. Shared by
#: `api/hub.py`'s `get_project_info` (read) and `save_project_profile` below (write).
PROFILE_FIELD_MAP = {
	"project_stage": "custom_egc_project_stage",
	"sector": "custom_egc_sector",
	"delivery_method": "custom_egc_delivery_method",
	"contract_type": "custom_egc_contract_type",
	"project_description": "custom_egc_project_description",
	"project_image": "custom_egc_project_image",
	"project_address": "custom_project_address",
	"contract_date": "custom_egc_contract_date",
	"forecast_completion_date": "custom_egc_forecast_completion_date",
	"warranty_start_date": "custom_egc_warranty_start_date",
	"dlp_end_date": "custom_egc_dlp_end_date",
}

STAKEHOLDER_ROW_FIELDS = (
	"role",
	"person",
	"party_name",
	"organization_type",
	"organization",
	"email",
	"phone",
	"is_primary",
)
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

	# Covers both picking an existing (already-linked) Address and creating a brand new one via
	# this dialog's own Link-field quick-entry, which has no way to know about Project on its
	# own — see ensure_address_linked_to_project's own docstring. The native Project form's
	# equivalent (project.js) calls the same function from its own change handler, since a
	# native-form save never goes through this endpoint.
	if values.get("project_address"):
		ensure_address_linked_to_project(values["project_address"], project)


@frappe.whitelist()
def get_person_info(person: str) -> dict:
	"""Party Name/Organization/Email/Phone as they'd be filled in for `person` — the exact same
	resolution `EGCProjectStakeholder.fetch_from_person()` does on save (User's own fields,
	organization via `directory.resolve_organization`'s Portal User lookup), exposed so the Hub's
	own "Add to Directory"/"Add Person" dialogs can show it live the moment `person` is picked,
	not only after the record is actually created."""
	if not person:
		return {}
	user = frappe.db.get_value("User", person, ["full_name", "email", "phone", "mobile_no"], as_dict=True)
	if not user:
		return {}
	org = directory.resolve_organization(person)
	organization_type, organization = org if org else (None, None)
	organization_name = None
	if organization:
		name_field = "supplier_name" if organization_type == "Supplier" else "customer_name"
		organization_name = frappe.db.get_value(organization_type, organization, name_field)
	return {
		"party_name": user.full_name,
		"organization_type": organization_type,
		"organization": organization,
		"organization_name": organization_name,
		"email": user.email,
		"phone": user.phone or user.mobile_no,
	}


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
		info = get_person_info(row_values["person"])
		if info:
			row_values["party_name"] = row_values.get("party_name") or info["party_name"]
			if not row_values.get("organization"):
				row_values["organization_type"] = info["organization_type"]
				row_values["organization"] = info["organization"]
			row_values["email"] = row_values.get("email") or info["email"]
			row_values["phone"] = row_values.get("phone") or info["phone"]
	# `organization_type` (when `organization` is set directly, no `person`) field-defaults to
	# "Customer" on the child doctype itself — that applies on every save regardless of entry
	# path (this endpoint, the native form, ...), so it isn't duplicated here.

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


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_addresses_for_project(doctype, txt, searchfield, start, page_len, filters):
	"""Link-field query for `Project.custom_project_address` — `Address` has no direct FK to
	`Project` (core's own `Dynamic Link` child-table pattern, `Address.links`, is how any
	doctype gets address support), so this joins through it rather than filtering a plain
	field. Only offers Addresses already linked to THIS project; `ensure_address_linked_to_project`
	below is what creates that link in the first place, whether for a pre-existing Address or
	one just created via this field's own quick-entry."""
	project = (filters or {}).get("project")
	if not project:
		return []
	return frappe.db.sql(
		"""
		select a.name, a.address_title
		from `tabAddress` a
		inner join `tabDynamic Link` dl on dl.parent = a.name and dl.parenttype = 'Address'
		where dl.link_doctype = 'Project' and dl.link_name = %(project)s
			and a.name like %(txt)s
		order by a.name
		limit %(page_len)s offset %(start)s
		""",
		{"project": project, "txt": f"%{txt}%", "start": start, "page_len": page_len},
	)


@frappe.whitelist()
def ensure_address_linked_to_project(address: str, project: str) -> None:
	"""Idempotently links `address` back to `project` via a `Dynamic Link` row, so it satisfies
	`get_addresses_for_project`'s own filter on future searches. Called from `project.js` on
	`custom_project_address` change — covers both "picked an existing Address" (already linked,
	no-op) and "created a brand new one via the field's own quick-entry" (not linked yet) the
	same way, without needing to intercept the quick-entry dialog itself."""
	if not address or not project:
		return
	_require_profile_edit_access(project)
	already_linked = frappe.db.exists(
		"Dynamic Link",
		{"parent": address, "parenttype": "Address", "link_doctype": "Project", "link_name": project},
	)
	if already_linked:
		return
	doc = frappe.get_doc("Address", address)
	doc.append("links", {"link_doctype": "Project", "link_name": project})
	doc.save(ignore_permissions=True)


def resolve_role_user(project: str, role_name: str) -> str | None:
	"""The `person` (a User, directly) of the project's stakeholder row for `role_name`, or None.

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
		fields=["person"],
		order_by="is_primary desc, idx asc",
		limit=1,
	)
	return rows[0].person or None if rows else None


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
