# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for Level 1 §30 ("Project Directory Must Be Used Everywhere"): `EGC Submittal`'s
`responsible_organization`/`received_from_person` and `EGC Project Document`'s
`originator_person` — each keeps its matching free-text field (`responsible_party`/
`received_from`/`originator`) mirroring the linked Directory record, the same
`fetch_from_person`-style discipline `EGC Project Stakeholder` already uses. The free-text field
stays directly settable only when no Directory reference is linked — the "controlled free-text
fallback" the spec explicitly asks for.
"""

import frappe
from frappe.tests import IntegrationTestCase


def _get_or_create_company():
	existing = frappe.db.get_value("Company", {}, "name")
	if existing:
		return existing
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "EGC Directory Integration Test Co",
			"abbr": "EDITC",
			"default_currency": "USD",
			"country": "United Arab Emirates",
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def _make_project():
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-DirInt-Test-{frappe.generate_hash(length=8)}",
			"company": _get_or_create_company(),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_organization(customer_name=None):
	customer_name = customer_name or f"EGC-DirInt-Org-{frappe.generate_hash(length=6)}"
	existing = frappe.db.get_value("Customer", {"customer_name": customer_name})
	if existing:
		return existing
	doc = frappe.get_doc(
		{"doctype": "Customer", "customer_name": customer_name, "custom_organization_type": "Subcontractor"}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_person(full_name=None):
	# See test_directory.py's own `_make_person` docstring — passing the display name straight as
	# `first_name` reproduces the same `full_name` on Contact for these single-string test names.
	doc = frappe.get_doc(
		{"doctype": "Contact", "first_name": full_name or f"EGC-DirInt-Person-{frappe.generate_hash(length=6)}"}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_master(doctype, fieldname, value, **extra):
	if frappe.db.exists(doctype, value):
		return value
	frappe.get_doc({"doctype": doctype, fieldname: value, **extra}).insert(ignore_permissions=True)
	return value


class TestSubmittalDirectoryIntegration(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.submittal_type = _get_or_create_master(
			"EGC Submittal Type", "submittal_type_name", "EGC-DirInt Shop Drawing", abbreviation="DIT"
		)

	def setUp(self):
		self.project = _make_project()

	def _make_submittal(self, submittal_number="SUB-DI-001", **kwargs):
		values = {
			"doctype": "EGC Submittal",
			"project": self.project,
			"submittal_number": submittal_number,
			"title": submittal_number,
			"submittal_type": self.submittal_type,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def test_responsible_organization_fills_responsible_party(self):
		customer_name = "EGC-DirInt-ABC-MEP"
		org = _make_organization(customer_name)
		doc = self._make_submittal(responsible_organization=org)
		self.assertEqual(doc.responsible_party, customer_name)

	def test_free_text_responsible_party_allowed_without_organization(self):
		doc = self._make_submittal(responsible_party="A one-off subcontractor not in the Directory")
		self.assertIsNone(doc.responsible_organization)
		self.assertEqual(doc.responsible_party, "A one-off subcontractor not in the Directory")

	def test_responsible_party_always_mirrors_organization_once_linked(self):
		customer_name = "EGC-DirInt-XYZ-Consult"
		org = _make_organization(customer_name)
		doc = self._make_submittal(responsible_organization=org, responsible_party="Stale Free-Text Name")
		# The Directory reference wins — same discipline as EGCProjectStakeholder.fetch_from_person,
		# not a "fill only if blank" default.
		self.assertEqual(doc.responsible_party, customer_name)

	def test_received_from_person_fills_received_from(self):
		person_name = "Ahmed Hassan Test Consultant"
		person = _make_person(person_name)
		doc = self._make_submittal(submittal_number="SUB-DI-002", received_from_person=person)
		self.assertEqual(doc.received_from, person_name)

	def test_edit_reflects_updated_organization_name(self):
		org = _make_organization("EGC-DirInt-Rename-Co")
		doc = self._make_submittal(submittal_number="SUB-DI-003", responsible_organization=org)
		self.assertEqual(doc.responsible_party, "EGC-DirInt-Rename-Co")

		frappe.db.set_value("Customer", org, "customer_name", "EGC-DirInt-Renamed-Co")
		doc.save(ignore_permissions=True)  # validate() re-fetches on every save, changed or not
		self.assertEqual(doc.responsible_party, "EGC-DirInt-Renamed-Co")


class TestDocumentDirectoryIntegration(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.document_type = _get_or_create_master(
			"EGC Document Type", "document_type_name", "EGC-DirInt Drawing", abbreviation="DID"
		)

	def setUp(self):
		self.project = _make_project()

	def _make_document(self, document_number="DOC-DI-001", **kwargs):
		values = {
			"doctype": "EGC Project Document",
			"project": self.project,
			"document_number": document_number,
			"title": document_number,
			"document_type": self.document_type,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def test_originator_person_fills_originator(self):
		person_name = "John Miller Test OEM"
		person = _make_person(person_name)
		doc = self._make_document(originator_person=person)
		self.assertEqual(doc.originator, person_name)

	def test_free_text_originator_allowed_without_person(self):
		doc = self._make_document(originator="A one-off originator not in the Directory")
		self.assertIsNone(doc.originator_person)
		self.assertEqual(doc.originator, "A one-off originator not in the Directory")

	def test_originator_always_mirrors_person_once_linked(self):
		person = _make_person("Stable Person Name")
		doc = self._make_document(originator_person=person, originator="Stale Free-Text Name")
		self.assertEqual(doc.originator, "Stable Person Name")
