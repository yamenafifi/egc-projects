"""Idempotent post-install / post-migrate setup: roles and classification masters.

Everything here is safe to run repeatedly — `after_migrate` calls it on every migration so a
site that upgrades from an earlier version of this app picks up newly-seeded master records
without a patch.
"""

import frappe

from egc_projects.egc_projects.constants import EGC_ROLES

DISCIPLINES = (
	("ARCH", "Architectural"),
	("MECH", "Mechanical"),
	("ELEC", "Electrical"),
	("CIVIL", "Civil"),
)

#: (name, abbreviation, is_drawing)
DOCUMENT_TYPES = (
	("Drawing", "DWG", 1),
	("Specification", "SPEC", 0),
	("Method Statement", "MS", 0),
	("Technical Data", "TD", 0),
	("Calculation", "CALC", 0),
	("Certificate", "CERT", 0),
	("Report", "RPT", 0),
	("Other", "OTH", 0),
)

#: (role_name, is_egc_internal) — ARCHITECTURE_V2.md §2
STAKEHOLDER_ROLES = (
	("Client", 0),
	("Main Contractor", 0),
	("Consultant", 0),
	("Architect", 0),
	("OEM", 0),
	("EGC Project Manager", 1),
	("EGC Site Manager", 1),
	("Project Engineer", 1),
	("Document Controller", 1),
	("QA/QC", 1),
	("HSE", 1),
	("Commercial", 1),
)

MODALITIES = (
	"MRI",
	"CT",
	"X-Ray",
	"Ultrasound",
	"Cath Lab",
	"Linear Accelerator",
	"Nuclear Medicine",
	"Other",
)

EQUIPMENT_MANUFACTURERS = (
	"Siemens Healthineers",
	"Philips Healthcare",
	"GE HealthCare",
	"Canon Medical",
	"Other",
)

#: (name, abbreviation)
SUBMITTAL_TYPES = (
	("Shop Drawing", "SD"),
	("Material Submittal", "MAT"),
	("Method Statement", "MS"),
	("Calculation", "CALC"),
	("Technical Data", "TD"),
	("Product Data", "PD"),
	("Sample", "SMP"),
	("Mockup", "MU"),
	("Certificate", "CERT"),
)


def after_install() -> None:
	setup()


def after_migrate() -> None:
	setup()


def setup() -> None:
	create_roles()
	create_disciplines()
	create_document_types()
	create_submittal_types()
	create_stakeholder_roles()
	create_modalities()
	create_equipment_manufacturers()
	create_project_custom_fields()
	create_activity_completion_method_option()
	frappe.db.commit()


def create_project_custom_fields() -> None:
	from egc_projects.egc_projects import project_custom_fields

	_remove_stale_project_field_order()
	project_custom_fields.create()


def _remove_stale_project_field_order() -> None:
	"""A `field_order` Property Setter on `Project` freezes the WHOLE doctype's field order as a
	static snapshot (written whenever anyone uses Desk's "Customize Form" to drag-reorder
	fields) — and `Meta.sort_fields()` treats that frozen snapshot as authoritative over the
	doctype's own JSON `field_order`, silently overriding it. A snapshot taken before this app's
	(or another app's) custom fields existed never includes them, so every `insert_after` this
	module declares is computed relative to a list that doesn't contain half its own anchor
	points — the exact bug that once pushed core's own `more_info_tab` to the very end of the
	native Project form, well past its own content. Deleting it here, before every
	`create_custom_fields` run, keeps the doctype's own (complete, correct) field_order
	authoritative, so this can't silently recur if Customize Form is ever used on Project again.
	"""
	name = frappe.db.get_value("Property Setter", {"doc_type": "Project", "property": "field_order"})
	if name:
		frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)


def create_activity_completion_method_option() -> None:
	"""Adds "Activity Completion" as a 5th option on core `Project.percent_complete_method`
	(Property Setter, not a Custom Field — this widens an existing Select's own options rather
	than adding a new field). See `project_progress.py` for why this app needs a value distinct
	from core's "Task Completion" at all. Idempotent: `make_property_setter` itself upserts by
	(doc_type, field_name, property), so re-running this is always safe."""
	from egc_projects.egc_projects.project_progress import PERCENT_COMPLETE_METHOD

	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	options = "Manual\nTask Completion\nTask Progress\nTask Weight\n" + PERCENT_COMPLETE_METHOD
	current = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Project", "field_name": "percent_complete_method", "property": "options"},
		"value",
	)
	if current == options:
		return
	make_property_setter("Project", "percent_complete_method", "options", options, "Text")


def create_roles() -> None:
	for role in EGC_ROLES:
		if frappe.db.exists("Role", role):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role,
				"desk_access": 1,
			}
		).insert(ignore_permissions=True)


def create_disciplines() -> None:
	if not frappe.db.table_exists("EGC Discipline"):
		return

	for code, name in DISCIPLINES:
		if frappe.db.exists("EGC Discipline", code):
			continue
		frappe.get_doc(
			{
				"doctype": "EGC Discipline",
				"discipline_code": code,
				"discipline_name": name,
			}
		).insert(ignore_permissions=True)


def create_document_types() -> None:
	if not frappe.db.table_exists("EGC Document Type"):
		return

	for name, abbreviation, is_drawing in DOCUMENT_TYPES:
		if frappe.db.exists("EGC Document Type", name):
			continue
		frappe.get_doc(
			{
				"doctype": "EGC Document Type",
				"document_type_name": name,
				"abbreviation": abbreviation,
				"is_drawing": is_drawing,
			}
		).insert(ignore_permissions=True)


def create_submittal_types() -> None:
	if not frappe.db.table_exists("EGC Submittal Type"):
		return

	for name, abbreviation in SUBMITTAL_TYPES:
		if frappe.db.exists("EGC Submittal Type", name):
			continue
		frappe.get_doc(
			{
				"doctype": "EGC Submittal Type",
				"submittal_type_name": name,
				"abbreviation": abbreviation,
			}
		).insert(ignore_permissions=True)


def create_stakeholder_roles() -> None:
	if not frappe.db.table_exists("EGC Stakeholder Role"):
		return

	for index, (role_name, is_egc_internal) in enumerate(STAKEHOLDER_ROLES):
		# `EGC Stakeholder Role` is named `field:role_name`, so a row created ad hoc by a user
		# or another agent under the same name is found and left untouched here rather than
		# duplicated or silently overwritten.
		if frappe.db.exists("EGC Stakeholder Role", role_name):
			continue
		frappe.get_doc(
			{
				"doctype": "EGC Stakeholder Role",
				"role_name": role_name,
				"is_egc_internal": is_egc_internal,
				"sequence": index,
			}
		).insert(ignore_permissions=True)


def create_modalities() -> None:
	if not frappe.db.table_exists("EGC Modality"):
		return

	for name in MODALITIES:
		if frappe.db.exists("EGC Modality", name):
			continue
		frappe.get_doc({"doctype": "EGC Modality", "modality_name": name}).insert(ignore_permissions=True)


def create_equipment_manufacturers() -> None:
	if not frappe.db.table_exists("EGC Equipment Manufacturer"):
		return

	for name in EQUIPMENT_MANUFACTURERS:
		if frappe.db.exists("EGC Equipment Manufacturer", name):
			continue
		frappe.get_doc({"doctype": "EGC Equipment Manufacturer", "manufacturer_name": name}).insert(
			ignore_permissions=True
		)
