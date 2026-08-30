# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for the Project Directory / multi-assignment foundation (Level 0 §3-6 of the
project-controls expansion): core `Customer`, core `Contact`, and the generic `EGC Assignment`
engine (assignments.py) that replaced EGC Activity's single `responsible_user`/
`responsible_supplier` fields.
"""

import frappe
from frappe.tests import IntegrationTestCase

from egc_projects.egc_projects import assignments


def _make_company():
	return frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]


def _make_project(company):
	doc = frappe.get_doc(
		{"doctype": "Project", "project_name": f"EGC-Dir-Test-{frappe.generate_hash(length=8)}", "company": company}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_activity(project, code):
	doc = frappe.get_doc(
		{"doctype": "EGC Activity", "project": project, "activity_code": code, "activity_name": code}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_submittal(project, number):
	submittal_type = "EGC-Dir-Test Submittal Type"
	if not frappe.db.exists("EGC Submittal Type", submittal_type):
		frappe.get_doc(
			{"doctype": "EGC Submittal Type", "submittal_type_name": submittal_type, "abbreviation": "DIRT"}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc(
		{
			"doctype": "EGC Submittal",
			"project": project,
			"submittal_number": number,
			"title": number,
			"submittal_type": submittal_type,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_organization(customer_name=None):
	customer_name = customer_name or f"EGC-Dir-Org-{frappe.generate_hash(length=6)}"
	existing = frappe.db.get_value("Customer", {"customer_name": customer_name})
	if existing:
		return existing
	doc = frappe.get_doc(
		{"doctype": "Customer", "customer_name": customer_name, "custom_organization_type": "Consultant"}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_person(full_name=None, organization=None, user=None):
	# `Contact.full_name` is derived from `first_name`/`middle_name`/`last_name` (never typed
	# directly) — passing the whole display name as `first_name` reproduces it exactly for these
	# single-string test names (Contact.autoname's own `_get_full_name()` just returns
	# `first_name` unchanged when middle/last are blank).
	doc = frappe.get_doc(
		{
			"doctype": "Contact",
			"first_name": full_name or f"Test Person {frappe.generate_hash(length=6)}",
			"user": user,
			"links": [{"link_doctype": "Customer", "link_name": organization}] if organization else [],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestEGCAssignment(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = _make_company()

	def setUp(self):
		frappe.set_user("Administrator")
		self.project = _make_project(self.company)
		self.activity = _make_activity(self.project, "DIR-ACT")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_person_or_organization_required(self):
		with self.assertRaises(frappe.ValidationError):
			assignments.add_assignment("EGC Activity", self.activity, "Responsible")

	def test_organization_only_assignment_allowed(self):
		org = _make_organization()
		name = assignments.add_assignment("EGC Activity", self.activity, "Contractor", organization=org)
		self.assertTrue(frappe.db.exists("EGC Assignment", name))

	def test_organization_fetched_from_person_when_blank(self):
		org = _make_organization()
		person = _make_person(organization=org)
		name = assignments.add_assignment("EGC Activity", self.activity, "Responsible", person=person)
		self.assertEqual(frappe.db.get_value("EGC Assignment", name, "organization"), org)

	def test_project_derived_from_parent_not_trusted_from_caller(self):
		person = _make_person()
		name = assignments.add_assignment("EGC Activity", self.activity, "Responsible", person=person)
		self.assertEqual(frappe.db.get_value("EGC Assignment", name, "project"), self.project)

	def test_disallowed_parent_doctype_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			assignments.add_assignment("Project", self.project, "Responsible", person=_make_person())

	def test_submittal_accepts_multiple_assignments(self):
		# Level 1 §31: "multiple responsible people, multiple organizations" on a Submittal —
		# EGC Submittal joined EGC Activity in ALLOWED_ASSIGNMENT_DOCTYPES this phase.
		submittal = _make_submittal(self.project, "DIR-SUB-001")
		org = _make_organization()
		p1 = _make_person("Ahmed", organization=org)
		p2 = _make_person("Sara", organization=org)

		assignments.add_assignment("EGC Submittal", submittal, "Responsible", person=p1, is_primary=True)
		assignments.add_assignment("EGC Submittal", submittal, "Watcher", person=p2)

		rows = assignments.get_assignments_for("EGC Submittal", submittal)
		self.assertEqual(len(rows), 2)
		self.assertEqual(frappe.db.get_value("EGC Assignment", rows[0]["name"], "project"), self.project)

	def test_same_person_same_role_twice_rejected(self):
		person = _make_person()
		assignments.add_assignment("EGC Activity", self.activity, "Responsible", person=person)
		# DuplicateEntryError, not ValidationError — matches EGC Activity Link's own convention
		# for exactly this kind of rejection (frappe.DuplicateEntryError extends NameError, not
		# ValidationError).
		with self.assertRaises(frappe.DuplicateEntryError):
			assignments.add_assignment("EGC Activity", self.activity, "Responsible", person=person)

	def test_same_person_different_role_allowed(self):
		# One person can genuinely hold two distinct roles on the same record (e.g. both
		# Responsible and Reviewer) — only the exact (person, role) pair must be unique.
		person = _make_person()
		assignments.add_assignment("EGC Activity", self.activity, "Responsible", person=person)
		name = assignments.add_assignment("EGC Activity", self.activity, "Reviewer", person=person)
		self.assertTrue(frappe.db.exists("EGC Assignment", name))

	def test_multiple_people_on_one_activity(self):
		# The whole point: several people, several organizations, one Activity.
		org_a = _make_organization("EGC-Dir-ABC-MEP")
		org_b = _make_organization("EGC-Dir-XYZ-Consult")
		p1 = _make_person("Ahmed", organization=org_a)
		p2 = _make_person("Sara", organization=org_b)
		assignments.add_assignment("EGC Activity", self.activity, "Responsible", person=p1, is_primary=True)
		assignments.add_assignment("EGC Activity", self.activity, "Consultant", person=p2)

		rows = assignments.get_assignments_for("EGC Activity", self.activity)
		self.assertEqual(len(rows), 2)
		roles = {r["assignment_role"] for r in rows}
		self.assertEqual(roles, {"Responsible", "Consultant"})
		primary = next(r for r in rows if r["is_primary"])
		self.assertEqual(primary["person_name"], "Ahmed")
		self.assertEqual(primary["organization_name"], "EGC-Dir-ABC-MEP")

	def test_remove_assignment(self):
		person = _make_person()
		name = assignments.add_assignment("EGC Activity", self.activity, "Watcher", person=person)
		assignments.remove_assignment(name)
		self.assertFalse(frappe.db.exists("EGC Assignment", name))

	def test_get_assignments_for_empty_when_none(self):
		self.assertEqual(assignments.get_assignments_for("EGC Activity", self.activity), [])
