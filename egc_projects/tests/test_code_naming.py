# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Regression coverage for `code_naming.py` — Discipline/Type-aware smart codes for Activity/
Document/Submittal, backed by Frappe's real `Series` counter, assigned server-side and never
directly user-editable. WBS is deliberately out of scope and has no tests here (see docs/
ARCHITECTURE.md)."""

import frappe
from frappe.tests import IntegrationTestCase

from egc_projects.egc_projects import code_naming


def _make_project():
	company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
	return frappe.get_doc(
		{"doctype": "Project", "project_name": f"EGC-CodeNaming-Test-{frappe.generate_hash(length=8)}", "company": company}
	).insert(ignore_permissions=True).name


def _get_or_create_discipline(code="ZZCN"):
	if frappe.db.exists("EGC Discipline", code):
		return code
	frappe.get_doc(
		{"doctype": "EGC Discipline", "discipline_code": code, "discipline_name": "EGC-CodeNaming-Test Discipline", "enabled": 1}
	).insert(ignore_permissions=True)
	return code


def _get_or_create_document_type(name="EGC-CodeNaming-Test Document Type", abbreviation="ZDW"):
	if frappe.db.exists("EGC Document Type", name):
		return name
	frappe.get_doc(
		{"doctype": "EGC Document Type", "document_type_name": name, "abbreviation": abbreviation, "enabled": 1}
	).insert(ignore_permissions=True)
	return name


def _get_or_create_submittal_type(name="EGC-CodeNaming-Test Submittal Type", abbreviation="ZSD"):
	if frappe.db.exists("EGC Submittal Type", name):
		return name
	frappe.get_doc(
		{"doctype": "EGC Submittal Type", "submittal_type_name": name, "abbreviation": abbreviation, "enabled": 1}
	).insert(ignore_permissions=True)
	return name


class TestSuggestActivityCode(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.discipline = _get_or_create_discipline()

	def setUp(self):
		self.project = _make_project()

	def _make_activity(self, discipline=None, activity_code=None):
		doc = frappe.get_doc(
			{
				"doctype": "EGC Activity",
				"project": self.project,
				"activity_code": activity_code,
				"activity_name": activity_code or "Test Activity",
				"discipline": discipline or self.discipline,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_fresh_scope_suggests_001(self):
		self.assertEqual(code_naming.suggest_activity_code(self.project, self.discipline), f"{self.discipline}-001")

	def test_peek_does_not_advance_the_series(self):
		first = code_naming.suggest_activity_code(self.project, self.discipline)
		second = code_naming.suggest_activity_code(self.project, self.discipline)
		self.assertEqual(first, second)

	def test_real_insert_assigns_and_advances_the_series(self):
		doc = self._make_activity()
		self.assertEqual(doc.activity_code, f"{self.discipline}-001")
		self.assertEqual(code_naming.suggest_activity_code(self.project, self.discipline), f"{self.discipline}-002")

	def test_explicit_code_is_preserved_and_does_not_advance_series(self):
		# A bulk-imported row supplying its own (e.g. client-legacy) code must be left exactly as
		# given, and must not perturb the auto-numbering series at all.
		doc = self._make_activity(activity_code="CLIENT-LEGACY-042")
		self.assertEqual(doc.activity_code, "CLIENT-LEGACY-042")
		self.assertEqual(code_naming.suggest_activity_code(self.project, self.discipline), f"{self.discipline}-001")

	def test_disciplines_scoped_independently(self):
		other_discipline = _get_or_create_discipline("ZZCO")
		self._make_activity()
		self.assertEqual(code_naming.suggest_activity_code(self.project, self.discipline), f"{self.discipline}-002")
		self.assertEqual(code_naming.suggest_activity_code(self.project, other_discipline), f"{other_discipline}-001")

	def test_projects_scoped_independently(self):
		other_project = _make_project()
		self._make_activity()
		self.assertEqual(code_naming.suggest_activity_code(self.project, self.discipline), f"{self.discipline}-002")
		self.assertEqual(code_naming.suggest_activity_code(other_project, self.discipline), f"{self.discipline}-001")

	def test_missing_required_fields_return_empty(self):
		self.assertEqual(code_naming.suggest_activity_code(self.project, None), "")
		self.assertEqual(code_naming.suggest_activity_code(None, self.discipline), "")


class TestSuggestDocumentCode(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.discipline = _get_or_create_discipline()
		cls.document_type = _get_or_create_document_type()

	def setUp(self):
		self.project = _make_project()

	def _make_document(self, document_number=None):
		doc = frappe.get_doc(
			{
				"doctype": "EGC Project Document",
				"project": self.project,
				"document_number": document_number,
				"title": "Test Document",
				"document_type": self.document_type,
				"discipline": self.discipline,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_fresh_scope_uses_abbreviation(self):
		expected = f"ZDW-{self.discipline}-001"
		self.assertEqual(
			code_naming.suggest_document_code(self.project, self.discipline, self.document_type), expected
		)

	def test_real_insert_assigns_and_advances_the_series(self):
		doc = self._make_document()
		self.assertEqual(doc.document_number, f"ZDW-{self.discipline}-001")
		self.assertEqual(
			code_naming.suggest_document_code(self.project, self.discipline, self.document_type),
			f"ZDW-{self.discipline}-002",
		)

	def test_explicit_code_is_preserved_and_does_not_advance_series(self):
		doc = self._make_document(document_number="CLIENT-LEGACY-DWG-042")
		self.assertEqual(doc.document_number, "CLIENT-LEGACY-DWG-042")
		self.assertEqual(
			code_naming.suggest_document_code(self.project, self.discipline, self.document_type),
			f"ZDW-{self.discipline}-001",
		)

	def test_missing_abbreviation_returns_empty(self):
		blank_type = "EGC-CodeNaming-Test Document Type No Abbr"
		if not frappe.db.exists("EGC Document Type", blank_type):
			frappe.get_doc(
				{"doctype": "EGC Document Type", "document_type_name": blank_type, "enabled": 1}
			).insert(ignore_permissions=True)
		self.assertEqual(code_naming.suggest_document_code(self.project, self.discipline, blank_type), "")

	def test_missing_required_fields_return_empty(self):
		self.assertEqual(code_naming.suggest_document_code(self.project, self.discipline, None), "")
		self.assertEqual(code_naming.suggest_document_code(self.project, None, self.document_type), "")


class TestSuggestSubmittalCode(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.discipline = _get_or_create_discipline()
		cls.submittal_type = _get_or_create_submittal_type()

	def setUp(self):
		self.project = _make_project()

	def _make_submittal(self, submittal_number=None):
		doc = frappe.get_doc(
			{
				"doctype": "EGC Submittal",
				"project": self.project,
				"submittal_number": submittal_number,
				"title": "Test Submittal",
				"submittal_type": self.submittal_type,
				"discipline": self.discipline,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def test_fresh_scope_uses_abbreviation(self):
		expected = f"ZSD-{self.discipline}-001"
		self.assertEqual(
			code_naming.suggest_submittal_code(self.project, self.discipline, self.submittal_type), expected
		)

	def test_real_insert_assigns_and_advances_the_series(self):
		doc = self._make_submittal()
		self.assertEqual(doc.submittal_number, f"ZSD-{self.discipline}-001")
		self.assertEqual(
			code_naming.suggest_submittal_code(self.project, self.discipline, self.submittal_type),
			f"ZSD-{self.discipline}-002",
		)

	def test_explicit_code_is_preserved_and_does_not_advance_series(self):
		doc = self._make_submittal(submittal_number="CLIENT-LEGACY-SD-042")
		self.assertEqual(doc.submittal_number, "CLIENT-LEGACY-SD-042")
		self.assertEqual(
			code_naming.suggest_submittal_code(self.project, self.discipline, self.submittal_type),
			f"ZSD-{self.discipline}-001",
		)

	def test_missing_required_fields_return_empty(self):
		self.assertEqual(code_naming.suggest_submittal_code(self.project, self.discipline, None), "")
		self.assertEqual(code_naming.suggest_submittal_code(self.project, None, self.submittal_type), "")
