# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for `api/documents.py` — the Hub's Documents tab (docs/ARCHITECTURE_V2.md §0 finding 4).

Fixture style matches `test_hub_api.py`/`test_document_control.py` exactly: shared masters in
`setUpClass`, a dedicated `Project` per test in `setUp`, private `.txt` File fixtures (a
fabricated `.pdf` body fails Frappe's PDF content scan on insert). EGC roles are additive and
grant nothing on core `Project` (docs/ARCHITECTURE.md §4), so every non-Administrator test user
carries a standard `Projects User` role in addition to whatever EGC role is under test.
"""

import frappe
from frappe.permissions import add_user_permission
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from egc_projects.api import documents
from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import relationships

#: The two `project`-first read/write endpoints; `get_document_detail`, `create_document_revision`
#: and `submit_document_revision` gate on a `document`/`revision`, not a `project`, and are
#: covered individually below (mirrors `test_hub_api.py`'s treatment of `get_document_revisions`).
_PROJECT_FIRST_ENDPOINTS = ("get_documents",)


class TestDocumentsAPI(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]
		cls.document_type = _get_or_create_document_type()
		cls.drawing_type = _get_or_create_drawing_type()
		cls.discipline = _get_or_create_discipline()
		cls.submittal_type = _get_or_create_submittal_type()

		cls.decoy_project = _make_project(cls.company)

		cls.manager_user = _get_or_create_user(
			"egc-docapi-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		# Passes the `Project` gate (`Projects User` grants write on core `Project`) but holds no
		# EGC role with `create` on `EGC Project Document` — proves the create endpoints' second
		# gate, not just the project gate, is what denies a read-only EGC user.
		cls.viewer_user = _get_or_create_user(
			"egc-docapi-viewer@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER]
		)
		cls.project_denied_user = _get_or_create_user(
			"egc-docapi-fenced@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		add_user_permission("Project", cls.decoy_project, cls.project_denied_user, ignore_permissions=True)

	def setUp(self):
		self.project = _make_project(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")

	# -- fixtures ------------------------------------------------------------------------------

	def _make_document(self, document_number="DOC-001", document_type=None, **kwargs):
		values = {
			"doctype": "EGC Project Document",
			"project": self.project,
			"document_number": document_number,
			"title": kwargs.pop("title", document_number),
			"document_type": document_type or self.document_type,
			"discipline": self.discipline,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_revision(self, document, revision, **kwargs):
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
		rev = self._make_revision(document, revision, **kwargs)
		rev.submit()
		return rev

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

	def _make_submission(self, submittal, revision_label, document_revisions=None, **kwargs):
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
		sub.insert(ignore_permissions=True)
		return sub

	# -- 1. get_documents surfaces every document type, not only drawings ------------------------

	def test_get_documents_includes_non_drawing_types(self):
		"""The whole point of the tab: a non-drawing document type must show up here too."""
		drawing = self._make_document("DA-DRW-001", document_type=self.drawing_type, title="A Drawing")
		method_statement = self._make_document(
			"DA-MS-001", document_type=self.document_type, title="A Method Statement"
		)

		rows = documents.get_documents(self.project)

		self.assertEqual({row.document for row in rows}, {drawing.name, method_statement.name})
		by_number = {row.document_number: row for row in rows}
		self.assertEqual(by_number["DA-DRW-001"].document_type, self.drawing_type)
		self.assertEqual(by_number["DA-MS-001"].document_type, self.document_type)

	def test_get_documents_reflects_current_revision_and_status(self):
		doc = self._make_document("DA-002")
		self._make_issued_revision(doc.name, "00")

		rows = documents.get_documents(self.project)
		row = next(r for r in rows if r.document == doc.name)
		self.assertEqual(row.current_revision_label, "00")
		self.assertEqual(row.document_status, c.DOCUMENT_ISSUED)
		self.assertEqual(row.approval_status, c.APPROVAL_NOT_SUBMITTED)

	# -- 2. Filter allow-list ----------------------------------------------------------------------

	def test_get_documents_filter_allow_list(self):
		self._make_document("DA-FLT-001", document_type=self.drawing_type)
		self._make_document("DA-FLT-002", document_type=self.document_type)

		with self.assertRaises(frappe.ValidationError):
			documents.get_documents(self.project, {"owner": "x"})
		with self.assertRaises(frappe.ValidationError):
			documents.get_documents(self.project, {"1=1": "x"})

		rows = documents.get_documents(self.project, {"document_type": self.drawing_type})
		self.assertEqual({row.document_number for row in rows}, {"DA-FLT-001"})

	# -- 3. get_document_detail: revisions, activities, submittals -------------------------------

	def test_get_document_detail_includes_revisions_activities_and_submittals(self):
		doc = self._make_document("DA-DETAIL-001")
		rev00 = self._make_issued_revision(doc.name, "00")

		# A submittal carrying rev00 while it is still current...
		submittal = self._make_submittal("DA-SUB-001")
		submission = self._make_submission(submittal.name, "00", document_revisions=[rev00.name])
		submission.submit()

		# ...then rev01 supersedes it. The submittal must still show up: "ever included", not
		# "currently includes" (docs/ARCHITECTURE_V2.md's own wording for this endpoint).
		self._make_issued_revision(doc.name, "01")

		activity = self._make_activity("DA-ACT-001")
		relationships.add_link(activity.name, "EGC Project Document", doc.name)

		detail = documents.get_document_detail(doc.name)

		self.assertEqual(detail["document"]["name"], doc.name)
		self.assertEqual(detail["document"]["current_revision_label"], "01")

		self.assertEqual([r["revision"] for r in detail["revisions"]], ["01", "00"])
		current_flags = {r["revision"]: r["is_current"] for r in detail["revisions"]}
		self.assertTrue(current_flags["01"])
		self.assertFalse(current_flags["00"])

		self.assertEqual([a["activity"] for a in detail["activities"]], [activity.name])

		self.assertEqual(len(detail["submittals"]), 1)
		self.assertEqual(detail["submittals"][0]["submittal"], submittal.name)
		self.assertEqual(detail["submittals"][0]["revision_label"], "00")

	def test_get_document_detail_not_found_raises(self):
		with self.assertRaises(frappe.DoesNotExistError):
			documents.get_document_detail("EGC-DOCAPI-Does-Not-Exist")

	# -- 4. create_document / create_document_revision / submit_document_revision round-trip -----

	def test_create_document_create_revision_and_submit_round_trip(self):
		frappe.set_user(self.manager_user)

		created = documents.create_document(
			project=self.project,
			document_number="DA-RT-001",
			title="Round Trip Document",
			document_type=self.document_type,
			discipline=self.discipline,
		)
		self.assertEqual(created["document_status"], c.DOCUMENT_NO_REVISION)
		document_name = created["name"]

		revision = documents.create_document_revision(
			document=document_name,
			revision="00",
			file=_make_private_file(),
			reason_for_revision="Initial issue",
		)
		self.assertEqual(revision["revision_status"], c.REVISION_DRAFT)
		self.assertEqual(revision["docstatus"], 0)

		# Not submitted yet: the document must already show Draft (the revision's own
		# `after_insert` calls `refresh_document_state`), but no current revision yet — matching
		# exactly what `document_control.refresh_document_state` alone would produce.
		self.assertEqual(
			frappe.db.get_value("EGC Project Document", document_name, "document_status"), c.DOCUMENT_DRAFT
		)
		self.assertFalse(frappe.db.get_value("EGC Project Document", document_name, "current_revision"))

		submitted = documents.submit_document_revision(revision["name"])
		self.assertEqual(submitted["revision_status"], c.REVISION_ISSUED)
		self.assertEqual(submitted["docstatus"], 1)

		# Assert the underlying engine state directly — not just this endpoint's own return
		# value — the same check `test_document_control.py` makes of `document_control.py` itself.
		doc_row = frappe.db.get_value(
			"EGC Project Document",
			document_name,
			["current_revision_label", "document_status", "approval_status", "current_file"],
			as_dict=True,
		)
		self.assertEqual(doc_row.current_revision_label, "00")
		self.assertEqual(doc_row.document_status, c.DOCUMENT_ISSUED)
		self.assertEqual(doc_row.approval_status, c.APPROVAL_NOT_SUBMITTED)
		self.assertEqual(doc_row.current_file, revision["file"])

	# -- 5. Project isolation ----------------------------------------------------------------------

	def test_project_isolation_denies_every_endpoint(self):
		doc = self._make_document("DA-ISO-001")
		rev = self._make_issued_revision(doc.name, "00")

		frappe.set_user(self.project_denied_user)

		for name in _PROJECT_FIRST_ENDPOINTS:
			endpoint = getattr(documents, name)
			with self.subTest(endpoint=name):
				with self.assertRaises(frappe.PermissionError):
					endpoint(self.project)

		with self.assertRaises(frappe.PermissionError):
			documents.get_document_detail(doc.name)
		with self.assertRaises(frappe.PermissionError):
			documents.create_document(
				project=self.project,
				document_number="DA-ISO-002",
				title="Should Not Insert",
				document_type=self.document_type,
			)
		with self.assertRaises(frappe.PermissionError):
			documents.create_document_revision(document=doc.name, revision="01", file=_make_private_file())
		with self.assertRaises(frappe.PermissionError):
			documents.submit_document_revision(rev.name)

	# -- 6. Write-permission gate on the create endpoints --------------------------------------------

	def test_create_document_and_revision_require_write_permission(self):
		doc = self._make_document("DA-PERM-001")

		frappe.set_user(self.viewer_user)

		with self.assertRaises(frappe.PermissionError):
			documents.create_document(
				project=self.project,
				document_number="DA-PERM-002",
				title="Viewer Cannot Create",
				document_type=self.document_type,
			)
		with self.assertRaises(frappe.PermissionError):
			documents.create_document_revision(document=doc.name, revision="00", file=_make_private_file())

		# The gate above is specific to creation, not a blanket project-permission failure — the
		# same viewer must still be able to read.
		documents.get_documents(self.project)
		documents.get_document_detail(doc.name)


def _get_or_create_document_type():
	name = "EGC-DOCAPI-Test Method Statement"
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


def _get_or_create_drawing_type():
	name = "EGC-DOCAPI-Test Drawing Type"
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


def _get_or_create_discipline():
	code = "ZZDA"
	if frappe.db.exists("EGC Discipline", code):
		return code
	frappe.get_doc(
		{
			"doctype": "EGC Discipline",
			"discipline_code": code,
			"discipline_name": "EGC-DOCAPI-Test Discipline",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return code


def _get_or_create_submittal_type():
	name = "EGC-DOCAPI-Test Submittal Type"
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


def _get_or_create_user(email, roles):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
			}
		)
		user.insert(ignore_permissions=True)
	user.add_roles(*roles)
	return user.name


def _make_project(company):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-DOCAPI-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_private_file():
	# Plain text, not .pdf: a fabricated PDF body fails Frappe's PDF malware/JS content scan on
	# insert. Content must be unique per file too, not just the name, since Frappe deduplicates
	# physical storage by content hash.
	token = frappe.generate_hash(length=8)
	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{token}.txt",
			"content": f"test documents api content {token}".encode(),
			"is_private": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.file_url
