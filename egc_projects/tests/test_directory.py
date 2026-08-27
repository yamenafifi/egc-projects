# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for the Project Directory / multi-assignment foundation (Level 0 §3-6 of the
project-controls expansion): `EGC Organization`, `EGC Person`, and the generic `EGC Assignment`
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


def _make_organization(name=None):
	name = name or f"EGC-Dir-Org-{frappe.generate_hash(length=6)}"
	if frappe.db.exists("EGC Organization", name):
		return name
	frappe.get_doc({"doctype": "EGC Organization", "organization_name": name, "organization_type": "Consultant"}).insert(
		ignore_permissions=True
	)
	return name


def _make_person(full_name=None, organization=None, user=None):
	doc = frappe.get_doc(
		{
			"doctype": "EGC Person",
			"full_name": full_name or f"Test Person {frappe.generate_hash(length=6)}",
			"organization": organization,
			"user": user,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestEGCPerson(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		# Not relying on inter-test rollback for a uniquely-constrained field (one User -> one
		# Person) — clean up explicitly so these tests are correct regardless of isolation mode.
		for name in frappe.get_all("EGC Person", filters={"user": self._test_user}, pluck="name"):
			frappe.delete_doc("EGC Person", name, ignore_permissions=True, force=True)

	_test_user = "Administrator"

	def test_email_fetched_from_user_when_blank(self):
		person = frappe.get_doc({"doctype": "EGC Person", "full_name": "Admin Person", "user": "Administrator"})
		person.insert(ignore_permissions=True)
		self.assertEqual(person.email, frappe.db.get_value("User", "Administrator", "email"))

	def test_explicit_email_not_overwritten(self):
		person = frappe.get_doc(
			{
				"doctype": "EGC Person",
				"full_name": "Custom Email Person",
				"user": "Administrator",
				"email": "custom@example.com",
			}
		)
		person.insert(ignore_permissions=True)
		self.assertEqual(person.email, "custom@example.com")

	def test_one_user_maps_to_at_most_one_person(self):
		_make_person(full_name="First Mapping", user="Administrator")
		with self.assertRaises(frappe.ValidationError):
			_make_person(full_name="Second Mapping", user="Administrator")


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
