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
	("Client Representative", 0),
	("Main Contractor", 0),
	("Consultant", 0),
	("Architect", 0),
	("OEM", 0),
	("OEM Engineer", 0),
	("Subcontractor Engineer", 0),
	("Supplier Representative", 0),
	("EGC Project Manager", 1),
	("EGC Site Manager", 1),
	("Project Engineer", 1),
	("Document Controller", 1),
	("QA/QC", 1),
	("HSE", 1),
	("Commercial", 1),
	("Quantity Surveyor", 1),
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
	trim_percent_complete_method_options()
	hide_unused_project_fields()
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


def trim_percent_complete_method_options() -> None:
	"""Narrows `Project.percent_complete_method`'s options down to the two EGC actually uses —
	`Manual` and `Activity Completion` (the option `create_activity_completion_method_option`
	above adds). Core's own `Task Completion`/`Task Progress`/`Task Weight` are meaningless here
	(EGC doesn't use Tasks) and stayed only because that function widens the list rather than
	replacing it. The field itself stays visible (not hidden) — `project_progress.py`'s
	auto-sync logic reads it, so it's a real choice a PM makes, not decoration. Unlike the dropped
	flat address fields, a project already holding one of the three removed values IS rewritten
	below (not left as a harmless stale value) — a Select field is validated against its own
	`options` on every save, so leaving it unchanged would make that project unsavable."""
	from egc_projects.egc_projects.project_progress import PERCENT_COMPLETE_METHOD

	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	# Core's own default ("Task Completion") is one of the three options about to be removed, and
	# Property Setter's own validate() checks the field's CURRENT default against a new `options`
	# value at save time — so the default has to change first, or saving the trimmed `options`
	# Property Setter itself fails immediately.
	#
	# The new default must be `PERCENT_COMPLETE_METHOD` ("Activity Completion"), NOT "Manual" —
	# `project_progress._should_sync()` treats "Task Completion" (core's original default) as its
	# own "nobody has explicitly decided anything yet, safe to auto-sync from EGC Activity"
	# sentinel (see that module's own docstring/comment); "Manual" is a genuine, deliberate
	# opt-out. Defaulting new projects to "Manual" would silently turn OFF the auto-sync every
	# existing project already gets today — confirmed by this exact regression breaking 4 of
	# `test_project_progress.py`'s own tests when first tried. "Activity Completion" is both a
	# valid trimmed-options value and preserves the sync-by-default behavior that already exists
	# and is already tested; it's a rename of the same role "Task Completion" played, not a
	# behavior change.
	current_default = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Project", "field_name": "percent_complete_method", "property": "default"},
		"value",
	)
	if current_default != PERCENT_COMPLETE_METHOD:
		make_property_setter("Project", "percent_complete_method", "default", PERCENT_COMPLETE_METHOD, "Text")

	options = f"Manual\n{PERCENT_COMPLETE_METHOD}"
	current_options = frappe.db.get_value(
		"Property Setter",
		{"doc_type": "Project", "field_name": "percent_complete_method", "property": "options"},
		"value",
	)
	if current_options != options:
		make_property_setter("Project", "percent_complete_method", "options", options, "Text")

	# A Select field's value is validated against its own `options` on every save, not just at
	# creation — so a project already holding one of the three removed values (from before this
	# ran) would fail to save at all from this point on, not just "keep a stale value" as
	# harmlessly as e.g. the dropped address fields do. Reset those rows rather than leave
	# existing projects unable to save until someone notices why — choosing the replacement that
	# preserves each one's CURRENT behavior instead of silently changing it:
	#   - "Task Completion" -> `PERCENT_COMPLETE_METHOD`: `_should_sync()` already treats these
	#     as equivalent (its own "auto-sync from Activities" sentinel), so this is a rename, not
	#     a behavior change.
	#   - "Task Progress"/"Task Weight" -> "Manual": `_should_sync()` returns False for both
	#     today (no case for them at all), same as it does for "Manual" — also a rename, not a
	#     behavior change.
	frappe.db.sql(
		"update `tabProject` set percent_complete_method = %(method)s where percent_complete_method = 'Task Completion'",
		{"method": PERCENT_COMPLETE_METHOD},
	)
	frappe.db.sql(
		"update `tabProject` set percent_complete_method = 'Manual'"
		" where percent_complete_method in ('Task Progress', 'Task Weight')"
	)


#: Core `Project` fields with zero references anywhere in this app (confirmed by search, not
#: assumed) — all either timesheet-specific ("(via Timesheet)" fields), a legacy scheduled-email
#: progress-collection feature (`monitor_progress_tab`'s own cluster), or generic ERPNext
#: concepts (Project Type/Priority/Template/Sales Order/Department/Cost Center) this app never
#: wired up. Hidden via Property Setter, never deleted — reversible, and hiding (unlike removing
#: a field from `field_order`) can't break `project_custom_fields.py`'s `custom_egc_details_bridge`
#: anchor at `actual_end_date`.
_HIDDEN_PROJECT_FIELDS = (
	"actual_start_date",
	"actual_end_date",
	"actual_time",
	"is_active",
	"project_template",
	"priority",
	"sales_order",
	"department",
	"cost_center",
	"monitor_progress_tab",
	"collect_progress",
	"holiday_list",
	"frequency",
	"from_time",
	"to_time",
	"first_email",
	"second_email",
	"daily_time_to_send",
	"day_to_send",
	"weekly_time_to_send",
	"subject",
	"message",
	# Native "Users" (Project User child table) — website-portal access mechanism this app
	# doesn't use (Directory-based access replaces it). Per explicit instruction: hidden, not
	# deleted — removed manually later.
	"users_section",
	"users",
	# egc_hr's own Supervisors table (attendance-approval authority, a distinct concern from the
	# Directory) — same instruction, same treatment. Hidden from here regardless of which app's
	# fixture created the field; a Property Setter only needs doc_type/field_name to target it.
	"custom_egc_supervisors_section",
	"custom_egc_supervisors",
)


def hide_unused_project_fields() -> None:
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for fieldname in _HIDDEN_PROJECT_FIELDS:
		current = frappe.db.get_value(
			"Property Setter", {"doc_type": "Project", "field_name": fieldname, "property": "hidden"}, "value"
		)
		if current == "1":
			continue
		make_property_setter("Project", fieldname, "hidden", 1, "Check")


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
