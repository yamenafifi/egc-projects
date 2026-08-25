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
	frappe.db.commit()


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
