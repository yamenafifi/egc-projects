# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from egc_projects.egc_projects import relationships
from egc_projects.egc_projects.constants import LINK_PURPOSE_REQUIREMENT


class TestRelationships(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# `add_link`/`remove_link` enforce permissions themselves via `frappe.has_permission`,
		# so the test session must actually hold them — Administrator bypasses the check outright,
		# matching the pattern used by `test_activity.py` / `test_wbs.py`.
		frappe.set_user("Administrator")

		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]
		cls.document_type = _get_or_create_document_type()
		cls.discipline = _get_or_create_discipline()
		cls.submittal_type = _get_or_create_submittal_type()

	def setUp(self):
		# A dedicated project per test avoids any cross-test collisions in `activity_code` /
		# `document_number` uniqueness, which is scoped per project.
		self.project = _make_project(self.company)

	def _make_activity(self, code, **kwargs):
		values = {
			"doctype": "EGC Activity",
			"project": self.project,
			"activity_code": code,
			"activity_name": kwargs.pop("activity_name", code),
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_document(self, document_number="DOC-001", project=None, **kwargs):
		values = {
			"doctype": "EGC Project Document",
			"project": project or self.project,
			"document_number": document_number,
			"title": kwargs.pop("title", document_number),
			"document_type": self.document_type,
			"discipline": self.discipline,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _issue_revision(self, document, revision="00"):
		rev = frappe.get_doc(
			{
				"doctype": "EGC Project Document Revision",
				"document": document,
				"revision": revision,
				"file": _make_private_file(),
				"revision_date": today(),
			}
		)
		rev.insert(ignore_permissions=True)
		rev.submit()
		return rev

	def _make_submittal(self, submittal_number="SUB-001", project=None, **kwargs):
		values = {
			"doctype": "EGC Submittal",
			"project": project or self.project,
			"submittal_number": submittal_number,
			"title": kwargs.pop("title", submittal_number),
			"submittal_type": self.submittal_type,
			"discipline": self.discipline,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _submittal_exists(self) -> bool:
		return frappe.db.table_exists("EGC Submittal")

	# -- 1. One approved-style drawing linked to three activities --------------------------

	def test_document_linked_to_three_activities(self):
		activity1 = self._make_activity("HVAC-F1", activity_name="Floor 1 Duct Installation")
		activity2 = self._make_activity("HVAC-F2", activity_name="Floor 2 Duct Installation")
		activity3 = self._make_activity("HVAC-F3", activity_name="Floor 3 Duct Installation")

		drawing = self._make_document("DWG-HVAC-001", title="HVAC Riser Diagram")
		self._issue_revision(drawing.name, "00")

		for activity in (activity1, activity2, activity3):
			relationships.add_link(activity.name, "EGC Project Document", drawing.name)

		for activity in (activity1, activity2, activity3):
			links = relationships.get_links_for_activity(activity.name)
			self.assertEqual(len(links), 1)
			self.assertEqual(links[0]["link_name"], drawing.name)
			self.assertEqual(links[0]["document_number"], "DWG-HVAC-001")
			self.assertEqual(links[0]["current_revision_label"], "00")

		related = relationships.get_activities_for("EGC Project Document", drawing.name)
		self.assertEqual(
			{row["activity"] for row in related},
			{activity1.name, activity2.name, activity3.name},
		)

	# -- 2. One submittal linked to multiple activities --------------------------------------

	def test_submittal_linked_to_multiple_activities(self):
		if not self._submittal_exists():
			self.skipTest("EGC Submittal does not exist on this site yet.")

		activity1 = self._make_activity("SUB-A1", activity_name="Submit Shop Drawing A")
		activity2 = self._make_activity("SUB-A2", activity_name="Submit Shop Drawing B")

		submittal = self._make_submittal("SUB-LINK-001", title="Chiller Shop Drawing")

		for activity in (activity1, activity2):
			relationships.add_link(activity.name, "EGC Submittal", submittal.name)

		for activity in (activity1, activity2):
			links = relationships.get_links_for_activity(activity.name)
			self.assertEqual(len(links), 1)
			self.assertEqual(links[0]["link_name"], submittal.name)
			self.assertEqual(links[0]["submittal_number"], "SUB-LINK-001")

		related = relationships.get_activities_for("EGC Submittal", submittal.name)
		self.assertEqual({row["activity"] for row in related}, {activity1.name, activity2.name})

	# -- 3. Cross-project link is rejected ----------------------------------------------------

	def test_cross_project_link_rejected(self):
		other_project = _make_project(self.company)
		activity = self._make_activity("XP-A1")
		document = self._make_document("XP-DOC-001", project=other_project)

		with self.assertRaises(frappe.ValidationError):
			relationships.add_link(activity.name, "EGC Project Document", document.name)

	def test_cross_project_rejected_at_controller_level_too(self):
		# Defense in depth: the controller's own `validate()` must reject this even when a
		# caller bypasses `relationships.add_link` entirely and inserts the row directly.
		other_project = _make_project(self.company)
		activity = self._make_activity("XP-A2")
		document = self._make_document("XP-DOC-002", project=other_project)

		link = frappe.get_doc(
			{
				"doctype": "EGC Activity Link",
				"activity": activity.name,
				"link_doctype": "EGC Project Document",
				"link_name": document.name,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			link.insert(ignore_permissions=True)

	# -- 4. A link_doctype outside the registry is rejected server-side ----------------------

	def test_disallowed_link_doctype_rejected_via_add_link(self):
		activity = self._make_activity("DL-A1")

		with self.assertRaises(frappe.ValidationError):
			relationships.add_link(activity.name, "Task", frappe.session.user)

	def test_disallowed_link_doctype_rejected_at_controller_level(self):
		activity = self._make_activity("DL-A2")

		link = frappe.get_doc(
			{
				"doctype": "EGC Activity Link",
				"activity": activity.name,
				"link_doctype": "User",
				"link_name": frappe.session.user,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			link.insert(ignore_permissions=True)

	# -- 5. Duplicate (activity, doctype, name) link is rejected ------------------------------

	def test_duplicate_link_rejected(self):
		activity = self._make_activity("DUP-A1")
		document = self._make_document("DUP-DOC-001")

		relationships.add_link(activity.name, "EGC Project Document", document.name)

		# `DuplicateEntryError` does NOT subclass `ValidationError` in Frappe — assert the exact
		# type so this test would fail loudly if the controller regressed to a plain throw.
		with self.assertRaises(frappe.DuplicateEntryError):
			relationships.add_link(activity.name, "EGC Project Document", document.name)

	# -- 6. get_links_for_activity surfaces the target's live status -------------------------

	def test_get_links_for_activity_returns_live_status(self):
		activity = self._make_activity("STAT-A1")
		document = self._make_document("STAT-DOC-001")
		self._issue_revision(document.name, "00")

		relationships.add_link(
			activity.name, "EGC Project Document", document.name, link_purpose=LINK_PURPOSE_REQUIREMENT
		)

		links = relationships.get_links_for_activity(activity.name)
		self.assertEqual(len(links), 1)
		row = links[0]
		self.assertEqual(row["link_purpose"], LINK_PURPOSE_REQUIREMENT)
		self.assertEqual(row["document_number"], "STAT-DOC-001")
		self.assertEqual(row["current_revision_label"], "00")
		self.assertIn("approval_status", row)

	# -- 7. add_link / remove_link round-trip --------------------------------------------------

	def test_add_remove_round_trip(self):
		activity = self._make_activity("RT-A1")
		document = self._make_document("RT-DOC-001")

		name = relationships.add_link(activity.name, "EGC Project Document", document.name)
		self.assertTrue(frappe.db.exists("EGC Activity Link", name))
		self.assertEqual(len(relationships.get_links_for_activity(activity.name)), 1)

		relationships.remove_link(name)
		self.assertFalse(frappe.db.exists("EGC Activity Link", name))
		self.assertEqual(relationships.get_links_for_activity(activity.name), [])


def _get_or_create_document_type():
	name = "EGC-REL-Test Document Type"
	if frappe.db.exists("EGC Document Type", name):
		return name
	frappe.get_doc(
		{
			"doctype": "EGC Document Type",
			"document_type_name": name,
			"abbreviation": "REL",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return name


def _get_or_create_discipline():
	code = "ZZRL"
	if frappe.db.exists("EGC Discipline", code):
		return code
	frappe.get_doc(
		{
			"doctype": "EGC Discipline",
			"discipline_code": code,
			"discipline_name": "EGC-REL-Test Discipline",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return code


def _get_or_create_submittal_type():
	if not frappe.db.table_exists("EGC Submittal Type"):
		return None
	name = "EGC-REL-Test Submittal Type"
	if frappe.db.exists("EGC Submittal Type", name):
		return name
	frappe.get_doc(
		{
			"doctype": "EGC Submittal Type",
			"submittal_type_name": name,
			"abbreviation": "REL",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return name


def _make_project(company):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-REL-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_private_file():
	# Plain text, not .pdf: a fabricated PDF body fails Frappe's PDF malware/JS content scan on
	# insert. Uniqueness matters because Frappe deduplicates physical storage by content hash.
	token = frappe.generate_hash(length=8)
	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{token}.txt",
			"content": f"test relationship layer content {token}".encode(),
			"is_private": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.file_url
