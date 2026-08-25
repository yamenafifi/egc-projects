# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import submittal_control


class TestSubmittal(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]
		cls.document_type = _get_or_create_document_type()
		cls.discipline = _get_or_create_discipline()
		cls.submittal_type = _get_or_create_submittal_type()

	def setUp(self):
		# Unique project name per test, so tests never collide; the whole class's writes are
		# rolled back by IntegrationTestCase once the module finishes.
		self.project = _make_project(self.company)

	# -- fixtures --------------------------------------------------------------------------

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

	def _make_draft_revision(self, document, revision, **kwargs):
		values = {
			"doctype": "EGC Project Document Revision",
			"document": document,
			"revision": revision,
			"file": _make_private_file(),
			"revision_date": today(),
		}
		values.update(kwargs)
		rev = frappe.get_doc(values)
		rev.insert(ignore_permissions=True)
		return rev

	def _make_issued_revision(self, document, revision, **kwargs):
		rev = self._make_draft_revision(document, revision, **kwargs)
		rev.submit()
		return rev

	def _make_submittal(self, submittal_number="SUB-001", **kwargs):
		values = {
			"doctype": "EGC Submittal",
			"project": self.project,
			"submittal_number": submittal_number,
			"title": kwargs.pop("title", submittal_number),
			"submittal_type": self.submittal_type,
			"discipline": self.discipline,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_submission(self, submittal, revision_label, document_revisions=None, insert=True, **kwargs):
		values = {
			"doctype": "EGC Submittal Revision",
			"submittal": submittal,
			"revision_label": revision_label,
			"date_submitted": today(),
		}
		values.update(kwargs)
		sub = frappe.get_doc(values)
		for rev_name in document_revisions or []:
			sub.append("documents", {"document_revision": rev_name})
		if insert:
			sub.insert(ignore_permissions=True)
		return sub

	# -- 1. Full acceptance scenario: two cycles, both remain visible ---------------------

	def test_full_acceptance_scenario_two_cycles_both_visible(self):
		doc = self._make_document("DOC-MECH-001")
		rev00 = self._make_issued_revision(doc.name, "00")

		submittal = self._make_submittal("SUB-MECH-0027", title="Mechanical Shop Drawing")

		sub_rev00 = self._make_submission(submittal.name, "00", document_revisions=[rev00.name])
		sub_rev00.submit()
		submittal_control.record_response(
			sub_rev00.name, c.RESPONSE_REVISE_AND_RESUBMIT, remarks="Fix ductwork clash"
		)

		sub_rev00.reload()
		self.assertEqual(sub_rev00.submission_status, c.SUBMISSION_RESPONDED)
		self.assertEqual(sub_rev00.response, c.RESPONSE_REVISE_AND_RESUBMIT)

		submittal.reload()
		self.assertEqual(submittal.submittal_status, c.RESPONSE_REVISE_AND_RESUBMIT)

		new_name = submittal_control.create_next_revision(submittal.name)
		sub_rev01 = frappe.get_doc("EGC Submittal Revision", new_name)
		self.assertEqual(sub_rev01.revision_label, "01")
		self.assertEqual(sub_rev01.submission_status, c.SUBMISSION_DRAFT)
		self.assertEqual(len(sub_rev01.documents), 0)  # nothing copied forward from Rev 00

		rev01 = self._make_issued_revision(doc.name, "01")
		sub_rev01.append("documents", {"document_revision": rev01.name})
		sub_rev01.save()
		sub_rev01.submit()
		submittal_control.record_response(sub_rev01.name, c.RESPONSE_APPROVED)

		# Rev 00 is untouched by everything that happened to Rev 01.
		sub_rev00.reload()
		self.assertEqual(sub_rev00.response, c.RESPONSE_REVISE_AND_RESUBMIT)

		sub_rev01.reload()
		self.assertEqual(sub_rev01.response, c.RESPONSE_APPROVED)

		submittal.reload()
		self.assertEqual(submittal.current_submission, sub_rev01.name)
		self.assertEqual(submittal.current_submission_label, "01")
		self.assertEqual(submittal.submittal_status, c.RESPONSE_APPROVED)

		all_labels = frappe.get_all(
			"EGC Submittal Revision", filters={"submittal": submittal.name}, pluck="revision_label"
		)
		self.assertCountEqual(all_labels, ["00", "01"])

	# -- 2. Document side of the scenario: the anti-conflict rule -------------------------

	def test_anti_conflict_rule_document_approval_status(self):
		doc = self._make_document("DOC-MECH-002")
		rev00 = self._make_issued_revision(doc.name, "00")

		submittal = self._make_submittal("SUB-MECH-0028")
		sub_rev00 = self._make_submission(submittal.name, "00", document_revisions=[rev00.name])
		sub_rev00.submit()
		submittal_control.record_response(sub_rev00.name, c.RESPONSE_REVISE_AND_RESUBMIT)

		doc.reload()
		self.assertEqual(doc.approval_status, c.RESPONSE_REVISE_AND_RESUBMIT)

		# Rev 01 is issued (becomes current) but has not been submitted for review of its own —
		# it must NOT inherit Rev 00's Revise & Resubmit. This is the single most important
		# assertion in this work package.
		self._make_issued_revision(doc.name, "01")

		doc.reload()
		self.assertIn(doc.approval_status, (c.APPROVAL_NOT_SUBMITTED, c.APPROVAL_UNDER_REVIEW))
		self.assertNotEqual(doc.approval_status, c.RESPONSE_REVISE_AND_RESUBMIT)

	# -- 3. Empty documents table rejected on submit ---------------------------------------

	def test_submit_with_no_documents_rejected(self):
		submittal = self._make_submittal("SUB-003")
		sub = self._make_submission(submittal.name, "00")
		with self.assertRaises(frappe.ValidationError):
			sub.submit()

	# -- 4. Draft (unissued) document revision cannot be submitted for review -------------

	def test_submit_referencing_draft_revision_rejected(self):
		doc = self._make_document("DOC-004")
		draft_rev = self._make_draft_revision(doc.name, "00")

		submittal = self._make_submittal("SUB-004")
		sub = self._make_submission(submittal.name, "00", document_revisions=[draft_rev.name])
		with self.assertRaises(frappe.ValidationError):
			sub.submit()

	# -- 5. Cross-project document revision rejected ----------------------------------------

	def test_cross_project_document_revision_rejected(self):
		other_project = _make_project(self.company)
		other_doc = self._make_document("DOC-OTHER-001", project=other_project)
		other_rev = self._make_issued_revision(other_doc.name, "00")

		submittal = self._make_submittal("SUB-005")
		sub = self._make_submission(
			submittal.name, "00", document_revisions=[other_rev.name], insert=False
		)
		with self.assertRaises(frappe.ValidationError):
			sub.insert(ignore_permissions=True)

	# -- 6. Recording a response twice on the same submission is rejected -------------------

	def test_record_response_twice_rejected(self):
		doc = self._make_document("DOC-006")
		rev00 = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-006")
		sub = self._make_submission(submittal.name, "00", document_revisions=[rev00.name])
		sub.submit()

		submittal_control.record_response(sub.name, c.RESPONSE_APPROVED)
		with self.assertRaises(frappe.ValidationError):
			submittal_control.record_response(sub.name, c.RESPONSE_APPROVED)

	# -- 7. create_next_revision before a response exists is rejected -----------------------

	def test_create_next_revision_before_response_rejected(self):
		doc = self._make_document("DOC-007")
		rev00 = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-007")
		sub = self._make_submission(submittal.name, "00", document_revisions=[rev00.name])
		sub.submit()

		with self.assertRaises(frappe.ValidationError):
			submittal_control.create_next_revision(submittal.name)

	# -- 8. Direct writes of engine-owned fields are rejected --------------------------------

	def test_direct_write_of_response_after_submit_rejected(self):
		doc = self._make_document("DOC-008")
		rev00 = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-008")
		sub = self._make_submission(submittal.name, "00", document_revisions=[rev00.name])
		sub.submit()

		sub.reload()
		sub.response = c.RESPONSE_APPROVED
		with self.assertRaises(frappe.ValidationError):
			sub.save()

	def test_direct_write_of_submission_status_before_submit_rejected(self):
		submittal = self._make_submittal("SUB-008B")
		sub = self._make_submission(submittal.name, "00")

		sub.submission_status = c.SUBMISSION_SUBMITTED
		with self.assertRaises(frappe.ValidationError):
			sub.save()

	# -- 9. Deletion rules ---------------------------------------------------------------------

	def test_delete_draft_succeeds_submitted_and_cancelled_are_blocked(self):
		doc = self._make_document("DOC-009")
		rev00 = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-009")

		draft = self._make_submission(submittal.name, "00")
		frappe.delete_doc("EGC Submittal Revision", draft.name, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("EGC Submittal Revision", draft.name))

		submitted = self._make_submission(submittal.name, "01", document_revisions=[rev00.name])
		submitted.submit()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("EGC Submittal Revision", submitted.name, ignore_permissions=True)

		submitted.reload()
		submitted.cancel()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("EGC Submittal Revision", submitted.name, ignore_permissions=True)

	# -- 10. Duplicate revision_label on the same submittal rejected ------------------------

	def test_duplicate_revision_label_same_submittal_rejected(self):
		submittal = self._make_submittal("SUB-010")
		self._make_submission(submittal.name, "00")

		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_submission(submittal.name, "00")

	def test_same_revision_label_on_different_submittal_is_fine(self):
		submittal_a = self._make_submittal("SUB-010A")
		submittal_b = self._make_submittal("SUB-010B")

		self._make_submission(submittal_a.name, "00")
		# must not raise
		self._make_submission(submittal_b.name, "00")


def _get_or_create_document_type():
	name = "EGC-SUB-Test Document Type"
	if frappe.db.exists("EGC Document Type", name):
		return name
	frappe.get_doc(
		{
			"doctype": "EGC Document Type",
			"document_type_name": name,
			"abbreviation": "TST",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return name


def _get_or_create_discipline():
	code = "ZZSB"
	if frappe.db.exists("EGC Discipline", code):
		return code
	frappe.get_doc(
		{
			"doctype": "EGC Discipline",
			"discipline_code": code,
			"discipline_name": "EGC-SUB-Test Discipline",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return code


def _get_or_create_submittal_type():
	name = "EGC-SUB-Test Submittal Type"
	if frappe.db.exists("EGC Submittal Type", name):
		return name
	frappe.get_doc(
		{
			"doctype": "EGC Submittal Type",
			"submittal_type_name": name,
			"abbreviation": "TST",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return name


def _make_project(company):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-SUB-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_private_file():
	# Plain text, not .pdf: a fabricated PDF body fails Frappe's PDF malware/JS content scan
	# on insert. The controlled-document fields don't care about content, only that it's a
	# real, private File record with a real file_url.
	token = frappe.generate_hash(length=8)
	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{token}.txt",
			"content": f"test submittal content {token}".encode(),
			"is_private": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.file_url
