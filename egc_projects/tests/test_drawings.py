# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for Wave D: Drawing Sets/Areas and the publish-readiness metadata
(docs/ARCHITECTURE_V2.md §9). Fixture style matches `test_documents_api.py` exactly.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from egc_projects.api import documents
from egc_projects.api import hub


class TestDrawings(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]
		cls.drawing_type = _get_or_create_drawing_type()
		cls.document_type = _get_or_create_document_type()

	def setUp(self):
		self.project = _make_project(self.company)
		self.other_project = _make_project(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")

	# -- fixtures ------------------------------------------------------------------------------

	def _make_set(self, set_code="S1", project=None, **kwargs):
		values = {
			"doctype": "EGC Drawing Set",
			"project": project or self.project,
			"set_code": set_code,
			"set_name": kwargs.pop("set_name", set_code),
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_area(self, area_code="A1", project=None, **kwargs):
		values = {
			"doctype": "EGC Drawing Area",
			"project": project or self.project,
			"area_code": area_code,
			"area_name": kwargs.pop("area_name", area_code),
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_document(self, document_number="DOC-001", document_type=None, **kwargs):
		values = {
			"doctype": "EGC Project Document",
			"project": self.project,
			"document_number": document_number,
			"title": kwargs.pop("title", document_number),
			"document_type": document_type or self.drawing_type,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_private_file(self):
		token = frappe.generate_hash(length=8)
		doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{token}.txt",
				"content": f"test drawings content {token}".encode(),
				"is_private": 1,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.file_url

	# -- EGC Drawing Set / EGC Drawing Area: uniqueness and project isolation --------------------

	def test_set_code_unique_per_project_only(self):
		self._make_set("DUP", project=self.project)
		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_set("DUP", project=self.project)
		# Same code in a different project is fine — scoped, not global.
		self._make_set("DUP", project=self.other_project)

	def test_area_code_unique_per_project_only(self):
		self._make_area("DUP", project=self.project)
		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_area("DUP", project=self.project)
		self._make_area("DUP", project=self.other_project)

	def test_area_wbs_node_cross_project_rejected(self):
		other_wbs = frappe.get_doc(
			{
				"doctype": "EGC WBS Node",
				"project": self.other_project,
				"wbs_code": "W1",
				"wbs_name": "Other Project Node",
			}
		)
		other_wbs.insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			self._make_area("A-XP", project=self.project, wbs_node=other_wbs.name)

	# -- EGC Project Document: drawing_set/drawing_area cross-project rejection ------------------

	def test_document_drawing_set_cross_project_rejected(self):
		other_set = self._make_set("OS1", project=self.other_project)
		with self.assertRaises(frappe.ValidationError):
			self._make_document("DOC-XP-1", drawing_set=other_set.name)

	def test_document_drawing_area_cross_project_rejected(self):
		other_area = self._make_area("OA1", project=self.other_project)
		with self.assertRaises(frappe.ValidationError):
			self._make_document("DOC-XP-2", drawing_area=other_area.name)

	def test_document_drawing_set_and_area_same_project_accepted(self):
		drawing_set = self._make_set("S1", project=self.project)
		area = self._make_area("A1", project=self.project)
		doc = self._make_document(
			"DOC-OK-1",
			drawing_set=drawing_set.name,
			drawing_area=area.name,
			drawing_date=today(),
			received_date=today(),
		)
		self.assertEqual(doc.drawing_set, drawing_set.name)
		self.assertEqual(doc.drawing_area, area.name)

	# -- api/hub.py get_drawings: new fields and filters ------------------------------------------

	def test_get_drawings_includes_set_area_fields_and_filters(self):
		drawing_set = self._make_set("S1", project=self.project)
		area = self._make_area("A1", project=self.project)
		in_set = self._make_document("DOC-SET-1", drawing_set=drawing_set.name, drawing_area=area.name)
		self._make_document("DOC-SET-2")  # no set/area

		rows = hub.get_drawings(self.project)
		by_number = {row.number: row for row in rows}
		self.assertEqual(by_number["DOC-SET-1"].drawing_set, drawing_set.name)
		self.assertEqual(by_number["DOC-SET-1"].drawing_area, area.name)
		self.assertIsNone(by_number["DOC-SET-2"].drawing_set)

		filtered = hub.get_drawings(self.project, {"drawing_set": drawing_set.name})
		self.assertEqual({row.document for row in filtered}, {in_set.name})

		filtered_area = hub.get_drawings(self.project, {"drawing_area": area.name})
		self.assertEqual({row.document for row in filtered_area}, {in_set.name})

	# -- api/documents.py: is_drawing flag, create_document drawing fields, readiness ------------

	def test_get_document_detail_is_drawing_flag(self):
		drawing = self._make_document("DOC-ISDRW-1", document_type=self.drawing_type)
		non_drawing = self._make_document("DOC-ISDRW-2", document_type=self.document_type)

		self.assertTrue(documents.get_document_detail(drawing.name)["document"]["is_drawing"])
		self.assertFalse(documents.get_document_detail(non_drawing.name)["document"]["is_drawing"])

	def test_create_document_accepts_drawing_fields(self):
		drawing_set = self._make_set("S1", project=self.project)
		created = documents.create_document(
			project=self.project,
			document_number="DOC-CREATE-1",
			title="Created Drawing",
			document_type=self.drawing_type,
			drawing_set=drawing_set.name,
			drawing_date=today(),
		)
		self.assertEqual(created["drawing_set"], drawing_set.name)
		self.assertEqual(str(created["drawing_date"]), today())

	def test_revision_readiness_defaults_and_round_trip(self):
		doc = self._make_document("DOC-READY-1")
		revision = documents.create_document_revision(
			document=doc.name, revision="00", file=self._make_private_file()
		)
		self.assertEqual(revision["readiness"], "Uploaded")

		updated = documents.update_revision_readiness(revision["name"], "Reviewed")
		self.assertEqual(updated["readiness"], "Reviewed")

		updated = documents.update_revision_readiness(revision["name"], "Ready to Publish")
		self.assertEqual(updated["readiness"], "Ready to Publish")

	def test_revision_readiness_rejected_invalid_value(self):
		doc = self._make_document("DOC-READY-2")
		revision = documents.create_document_revision(
			document=doc.name, revision="00", file=self._make_private_file()
		)
		with self.assertRaises(frappe.ValidationError):
			documents.update_revision_readiness(revision["name"], "Not A Real Value")

	def test_revision_readiness_locked_after_submit(self):
		doc = self._make_document("DOC-READY-3")
		revision = documents.create_document_revision(
			document=doc.name, revision="00", file=self._make_private_file()
		)
		documents.submit_document_revision(revision["name"])

		with self.assertRaises(frappe.ValidationError):
			documents.update_revision_readiness(revision["name"], "Reviewed")


def _get_or_create_drawing_type():
	name = "EGC-DRWTEST-Drawing Type"
	if frappe.db.exists("EGC Document Type", name):
		return name
	frappe.get_doc(
		{
			"doctype": "EGC Document Type",
			"document_type_name": name,
			"abbreviation": "DRW",
			"is_drawing": 1,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return name


def _get_or_create_document_type():
	name = "EGC-DRWTEST-Method Statement"
	if frappe.db.exists("EGC Document Type", name):
		return name
	frappe.get_doc(
		{
			"doctype": "EGC Document Type",
			"document_type_name": name,
			"abbreviation": "MS",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return name


def _make_project(company):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-DRWTEST-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name
