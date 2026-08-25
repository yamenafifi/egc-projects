# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import document_control


class TestDocumentControl(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]
		cls.document_type = _get_or_create_document_type()
		cls.discipline = _get_or_create_discipline()

	def setUp(self):
		# Unique project name per test, so tests never collide; the whole class's writes are
		# rolled back by IntegrationTestCase once the module finishes (see `_rollback_db`).
		self.project = _make_project(self.company)

	def _make_document(self, document_number="DOC-001", **kwargs):
		values = {
			"doctype": "EGC Project Document",
			"project": self.project,
			"document_number": document_number,
			"title": kwargs.pop("title", document_number),
			"document_type": self.document_type,
			"discipline": self.discipline,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_revision(self, document, revision, file_url=None, insert=True, **kwargs):
		values = {
			"doctype": "EGC Project Document Revision",
			"document": document,
			"revision": revision,
			"file": file_url or _make_private_file(),
			"revision_date": today(),
		}
		values.update(kwargs)
		rev = frappe.get_doc(values)
		if insert:
			rev.insert(ignore_permissions=True)
		return rev

	# -- 1. Rev 00 issued ----------------------------------------------------------------

	def test_rev00_issued_sets_current_and_document_status(self):
		doc = self._make_document("DOC-001")
		rev00 = self._make_revision(doc.name, "00")
		rev00.submit()

		doc.reload()
		self.assertEqual(doc.current_revision, rev00.name)
		self.assertEqual(doc.current_revision_label, "00")
		self.assertEqual(doc.document_status, c.DOCUMENT_ISSUED)
		self.assertEqual(doc.approval_status, c.APPROVAL_NOT_SUBMITTED)

	# -- 2. Rev 01 supersedes Rev 00, history is preserved --------------------------------

	def test_rev01_supersedes_rev00_and_preserves_history(self):
		doc = self._make_document("DOC-002")
		rev00 = self._make_revision(doc.name, "00")
		rev00_file = rev00.file
		rev00.submit()

		rev01 = self._make_revision(doc.name, "01")
		rev01.submit()

		rev00.reload()
		self.assertEqual(rev00.revision_status, c.REVISION_SUPERSEDED)
		self.assertEqual(rev00.superseded_by, rev01.name)
		self.assertEqual(rev00.file, rev00_file)  # row and file are unchanged, still readable

		doc.reload()
		self.assertEqual(doc.current_revision, rev01.name)
		self.assertEqual(doc.current_revision_label, "01")
		self.assertEqual(doc.document_status, c.DOCUMENT_ISSUED)

	# -- 3. File on a submitted revision is immutable --------------------------------------

	def test_file_cannot_change_after_submit(self):
		doc = self._make_document("DOC-003")
		rev00 = self._make_revision(doc.name, "00")
		rev00.submit()

		rev00.reload()
		rev00.file = _make_private_file()
		with self.assertRaises(frappe.UpdateAfterSubmitError):
			rev00.save()

	# -- 4. revision_status cannot be rewritten from outside the engine --------------------

	def test_revision_status_guarded_after_submit(self):
		doc = self._make_document("DOC-004")
		rev00 = self._make_revision(doc.name, "00")
		rev00.submit()

		rev00.reload()
		rev00.revision_status = c.REVISION_CANCELLED
		with self.assertRaises(frappe.ValidationError):
			rev00.save()

	def test_revision_status_guarded_before_submit(self):
		doc = self._make_document("DOC-004B")
		rev00 = self._make_revision(doc.name, "00")

		rev00.revision_status = c.REVISION_ISSUED
		with self.assertRaises(frappe.ValidationError):
			rev00.save()

	# -- 5. Deletion rules -------------------------------------------------------------------

	def test_delete_draft_succeeds_issued_and_cancelled_are_blocked(self):
		doc = self._make_document("DOC-005")

		draft = self._make_revision(doc.name, "00")
		frappe.delete_doc("EGC Project Document Revision", draft.name, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("EGC Project Document Revision", draft.name))

		issued = self._make_revision(doc.name, "01")
		issued.submit()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("EGC Project Document Revision", issued.name, ignore_permissions=True)

		issued.reload()
		issued.cancel()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("EGC Project Document Revision", issued.name, ignore_permissions=True)

	def test_deleting_last_draft_reverts_document_to_no_revision(self):
		doc = self._make_document("DOC-005B")
		draft = self._make_revision(doc.name, "00")

		doc.reload()
		self.assertEqual(doc.document_status, c.DOCUMENT_DRAFT)

		frappe.delete_doc("EGC Project Document Revision", draft.name, ignore_permissions=True)

		doc.reload()
		self.assertEqual(doc.document_status, c.DOCUMENT_NO_REVISION)

	# -- 6. Revision label uniqueness -------------------------------------------------------

	def test_duplicate_revision_label_same_document_rejected(self):
		doc = self._make_document("DOC-006")
		self._make_revision(doc.name, "00")

		with self.assertRaises(frappe.DuplicateEntryError):
			self._make_revision(doc.name, "00")

	def test_same_revision_label_on_different_document_is_fine(self):
		doc_a = self._make_document("DOC-006A")
		doc_b = self._make_document("DOC-006B")

		self._make_revision(doc_a.name, "00")
		# must not raise
		self._make_revision(doc_b.name, "00")

	# -- 7. Cancelling the current revision restores the previous one -----------------------

	def test_cancel_current_revision_restores_previous(self):
		doc = self._make_document("DOC-007")
		rev00 = self._make_revision(doc.name, "00")
		rev00.submit()
		rev01 = self._make_revision(doc.name, "01")
		rev01.submit()

		rev01.reload()
		rev01.cancel()

		rev00.reload()
		self.assertEqual(rev00.revision_status, c.REVISION_ISSUED)
		self.assertFalse(rev00.superseded_by)

		doc.reload()
		self.assertEqual(doc.current_revision, rev00.name)
		self.assertEqual(doc.current_revision_label, "00")
		self.assertEqual(doc.document_status, c.DOCUMENT_ISSUED)

	# -- 8. Cross-project revision is rejected -----------------------------------------------

	def test_revision_project_must_match_document_project(self):
		other_project = _make_project(self.company)
		doc = self._make_document("DOC-008")

		rev = frappe.get_doc(
			{
				"doctype": "EGC Project Document Revision",
				"document": doc.name,
				"project": other_project,
				"revision": "00",
				"file": _make_private_file(),
				"revision_date": today(),
			}
		)
		with self.assertRaises(frappe.ValidationError):
			rev.insert(ignore_permissions=True, ignore_links=True)

	# -- 9. approval_status with no submittal reference --------------------------------------

	def test_approval_status_not_submitted_without_submittal(self):
		doc = self._make_document("DOC-009")
		rev00 = self._make_revision(doc.name, "00")
		rev00.submit()

		self.assertEqual(document_control.get_approval_status(doc.name), c.APPROVAL_NOT_SUBMITTED)

		doc.reload()
		self.assertEqual(doc.approval_status, c.APPROVAL_NOT_SUBMITTED)

	# -- 10. Out-of-order submission never demotes the current revision ----------------------

	def test_out_of_order_submit_does_not_demote_current(self):
		doc = self._make_document("DOC-010")
		# Created in order, so revision_seq follows 1, 2, 3 exactly like the labels —
		# `revision_seq`, not the label text, is the ordering authority.
		rev00 = self._make_revision(doc.name, "00")
		rev01 = self._make_revision(doc.name, "01")
		rev02 = self._make_revision(doc.name, "02")

		rev00.submit()
		rev02.submit()  # jumps ahead of rev01; becomes current (highest seq so far)
		rev01.submit()  # out-of-order: a lower revision_seq submitted after a higher one

		doc.reload()
		self.assertEqual(doc.current_revision, rev02.name)
		self.assertEqual(doc.current_revision_label, "02")

		rev01.reload()
		self.assertEqual(rev01.revision_status, c.REVISION_SUPERSEDED)
		self.assertEqual(rev01.superseded_by, rev02.name)

		rev02.reload()
		self.assertEqual(rev02.revision_status, c.REVISION_ISSUED)
		self.assertFalse(rev02.superseded_by)


def _get_or_create_document_type():
	name = "EGC-DC-Test Document Type"
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
	code = "ZZDC"
	if frappe.db.exists("EGC Discipline", code):
		return code
	frappe.get_doc(
		{
			"doctype": "EGC Discipline",
			"discipline_code": code,
			"discipline_name": "EGC-DC-Test Discipline",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return code


def _make_project(company):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-DC-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_private_file():
	# Plain text, not .pdf: a fabricated PDF body fails Frappe's PDF malware/JS content scan
	# on insert. The controlled-document fields don't care about content, only that it's a
	# real, private File record with a real file_url — which this exercises just as well.
	token = frappe.generate_hash(length=8)
	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{token}.txt",
			# Content must be unique per file too, not just the name: Frappe deduplicates
			# physical storage by content hash, which would otherwise make two distinct File
			# records share the same file_url and defeat the "file is immutable" test.
			"content": f"test controlled document content {token}".encode(),
			"is_private": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.file_url
