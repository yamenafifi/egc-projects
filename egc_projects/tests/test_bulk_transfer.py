# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for `api/bulk_transfer.py` — the Hub's own Export/Import buttons (WBS, Activities,
Submittals, Documents), built on top of Frappe's own Data Export/Data Import machinery.

Fixture style matches `test_hub_api.py`: one shared set of masters in `setUpClass`, a project
per test in `setUp`, a project-fenced user built the same way to prove access can't be bypassed.

`Importer.import_data` itself is mocked throughout — it's Frappe core's own, already-tested
machinery; what's actually novel and worth testing here is (1) the permission gate in front of
it, (2) the `mute_emails` mapping, and (3) `enforce_bulk_import_project`, the one thing Frappe's
own Importer has no concept of at all.
"""

from unittest.mock import patch

import frappe
from frappe.permissions import add_user_permission
from frappe.tests import IntegrationTestCase

from egc_projects.api import bulk_transfer
from egc_projects.egc_projects import constants as c


class _StubImportFile:
	def get_payloads_for_import(self):
		return []


class _StubImporter:
	"""Stands in for `DataImport.get_importer()`'s real return value — just enough surface
	(`import_file.get_payloads_for_import()`) for `DataImport.validate()`'s own
	`set_payload_count()` to run without actually reading `import_file` off disk."""

	import_file = _StubImportFile()


class TestBulkTransfer(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]

		cls.decoy_project = _make_project(cls.company)

		cls.manager_user = _get_or_create_user(
			"egc-bulk-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		# Holds a role that would normally grant create/import, but is fenced to a different
		# project — proves the Hub's own project gate, not just the DocType-level permission,
		# is what stands in the way.
		cls.project_denied_user = _get_or_create_user(
			"egc-bulk-fenced@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		add_user_permission("Project", cls.decoy_project, cls.project_denied_user, ignore_permissions=True)
		# Passes the project gate but holds no role with `create`/`import` on EGC Activity at all.
		cls.doctype_denied_user = _get_or_create_user(
			"egc-bulk-viewer@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER]
		)

	def setUp(self):
		self.project = _make_project(self.company)
		add_user_permission("Project", self.project, self.doctype_denied_user, ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.flags[bulk_transfer.BULK_IMPORT_PROJECT_FLAG] = None

	# -- doctype allow-list -------------------------------------------------------------------

	def test_disallowed_doctype_rejected_for_export(self):
		with self.assertRaises(frappe.ValidationError):
			bulk_transfer.get_export_template(self.project, "Project")

	def test_disallowed_doctype_rejected_for_import(self):
		with self.assertRaises(frappe.ValidationError):
			bulk_transfer.import_records(self.project, "Project", "/files/whatever.csv")

	# -- permission gating: project scope -------------------------------------------------------

	def test_import_denied_when_user_is_fenced_out_of_the_project(self):
		frappe.set_user(self.project_denied_user)
		with self.assertRaises(frappe.PermissionError):
			bulk_transfer.import_records(self.project, "EGC Activity", "/files/whatever.csv")

	# -- real export (Frappe's own Exporter, not mocked) ----------------------------------------
	#
	# Regression coverage for a real bug that reached production: `download_template` requires an
	# explicit `export_fields` map — `Exporter.__init__` unconditionally does
	# `self.export_fields.items()`, so a missing one is `AttributeError: 'NoneType' object has no
	# attribute 'items'`, not "export everything" (see `_all_export_fields`'s docstring). Every
	# permission test above mocks past this call entirely, so it slipped through untested; these
	# don't mock anything — they must produce real file bytes for every export-enabled doctype.

	def test_export_produces_real_file_content_for_every_doctype(self):
		frappe.set_user(self.manager_user)
		for doctype in bulk_transfer.ALLOWED_TRANSFER_DOCTYPES:
			with self.subTest(doctype=doctype):
				frappe.local.response = frappe._dict()
				bulk_transfer.get_export_template(self.project, doctype, "Excel", True)
				self.assertEqual(frappe.response.get("type"), "binary")
				self.assertTrue(frappe.response.get("filecontent"))

	def test_export_blank_template_produces_real_csv_content(self):
		frappe.set_user(self.manager_user)
		frappe.local.response = frappe._dict()
		bulk_transfer.get_export_template(self.project, "EGC Activity", "CSV", False)
		self.assertEqual(frappe.response.get("type"), "csv")
		self.assertIn("Activity Code", frappe.response.get("result"))

	def test_export_denied_when_user_is_fenced_out_of_the_project(self):
		frappe.set_user(self.project_denied_user)
		with self.assertRaises(frappe.PermissionError):
			bulk_transfer.get_export_template(self.project, "EGC Activity")

	def test_export_with_explicit_names_only_includes_those_rows(self):
		frappe.set_user(self.manager_user)
		kept = _make_activity(self.project, "BULK-EXPORT-KEEP")
		_make_activity(self.project, "BULK-EXPORT-DROP")

		frappe.local.response = frappe._dict()
		bulk_transfer.get_export_template(self.project, "EGC Activity", "CSV", names=[kept])
		rows = frappe.response["result"].splitlines()[1:]
		self.assertEqual(len(rows), 1)
		self.assertIn(kept, rows[0])

	# -- delete_records -------------------------------------------------------------------------

	def test_delete_records_removes_the_rows(self):
		frappe.set_user(self.manager_user)
		a = _make_activity(self.project, "BULK-DEL-A")
		b = _make_activity(self.project, "BULK-DEL-B")

		result = bulk_transfer.delete_records(self.project, "EGC Activity", [a, b])

		self.assertEqual(result["deleted_count"], 2)
		self.assertEqual(result["failure_count"], 0)
		self.assertFalse(frappe.db.exists("EGC Activity", a))
		self.assertFalse(frappe.db.exists("EGC Activity", b))

	def test_delete_records_rejects_a_row_from_a_different_project(self):
		frappe.set_user(self.manager_user)
		other_project = _make_project(self.company)
		foreign = _make_activity(other_project, "BULK-DEL-FOREIGN")

		result = bulk_transfer.delete_records(self.project, "EGC Activity", [foreign])

		self.assertEqual(result["deleted_count"], 0)
		self.assertEqual(result["failure_count"], 1)
		self.assertTrue(frappe.db.exists("EGC Activity", foreign))

	def test_delete_records_denied_without_delete_permission(self):
		# EGC Project Viewer has no delete permission on EGC Activity at all.
		frappe.set_user(self.doctype_denied_user)
		activity = _make_activity(self.project, "BULK-DEL-DENIED")
		with self.assertRaises(frappe.PermissionError):
			bulk_transfer.delete_records(self.project, "EGC Activity", [activity])

	def test_delete_records_denied_when_fenced_out_of_the_project(self):
		frappe.set_user(self.project_denied_user)
		with self.assertRaises(frappe.PermissionError):
			bulk_transfer.delete_records(self.project, "EGC Activity", ["whatever"])

	def test_delete_records_rejects_disallowed_doctype(self):
		with self.assertRaises(frappe.ValidationError):
			bulk_transfer.delete_records(self.project, "Project", [self.project])

	# -- permission gating: doctype scope --------------------------------------------------------

	def test_import_denied_without_create_permission_on_the_doctype(self):
		# EGC Project Viewer has read+export but not create/import on EGC Activity — the project
		# gate alone must not be enough.
		frappe.set_user(self.doctype_denied_user)
		with self.assertRaises(frappe.PermissionError):
			bulk_transfer.import_records(self.project, "EGC Activity", "/files/whatever.csv")

	# -- mute_emails / import_type wiring (Importer itself mocked out) --------------------------
	#
	# `DataImport.get_importer` is also stubbed: `data_import.insert()`'s own `validate()` calls
	# it (via `validate_import_file`/`set_payload_count`) to actually read `import_file` off disk
	# — replaced here since these tests care about bulk_transfer.py's own field-mapping logic,
	# not Frappe's (already-tested) file parsing, and `/files/whatever.csv` doesn't really exist.

	@patch("frappe.core.doctype.data_import.importer.Importer")
	@patch("frappe.core.doctype.data_import.data_import.DataImport.get_importer", lambda self: _StubImporter())
	def test_send_email_false_mutes_emails(self, mock_importer_cls):
		frappe.set_user(self.manager_user)
		bulk_transfer.import_records(self.project, "EGC Activity", "/files/whatever.csv", send_email=False)
		data_import = frappe.get_last_doc("Data Import", {"reference_doctype": "EGC Activity"})
		self.assertEqual(data_import.mute_emails, 1)

	@patch("frappe.core.doctype.data_import.importer.Importer")
	@patch("frappe.core.doctype.data_import.data_import.DataImport.get_importer", lambda self: _StubImporter())
	def test_send_email_true_unmutes_emails(self, mock_importer_cls):
		frappe.set_user(self.manager_user)
		bulk_transfer.import_records(self.project, "EGC Activity", "/files/whatever.csv", send_email=True)
		data_import = frappe.get_last_doc("Data Import", {"reference_doctype": "EGC Activity"})
		self.assertEqual(data_import.mute_emails, 0)

	@patch("frappe.core.doctype.data_import.importer.Importer")
	@patch("frappe.core.doctype.data_import.data_import.DataImport.get_importer", lambda self: _StubImporter())
	def test_update_existing_selects_the_right_import_type(self, mock_importer_cls):
		frappe.set_user(self.manager_user)
		bulk_transfer.import_records(self.project, "EGC Activity", "/files/whatever.csv", update_existing=True)
		data_import = frappe.get_last_doc("Data Import", {"reference_doctype": "EGC Activity"})
		self.assertEqual(data_import.import_type, "Update Existing Records")

	@patch("frappe.core.doctype.data_import.importer.Importer")
	@patch("frappe.core.doctype.data_import.data_import.DataImport.get_importer", lambda self: _StubImporter())
	def test_default_import_type_is_insert(self, mock_importer_cls):
		frappe.set_user(self.manager_user)
		bulk_transfer.import_records(self.project, "EGC Activity", "/files/whatever.csv")
		data_import = frappe.get_last_doc("Data Import", {"reference_doctype": "EGC Activity"})
		self.assertEqual(data_import.import_type, "Insert New Records")

	@patch("frappe.core.doctype.data_import.importer.Importer")
	@patch("frappe.core.doctype.data_import.data_import.DataImport.get_importer", lambda self: _StubImporter())
	def test_project_flag_is_set_during_import_and_cleared_after(self, mock_importer_cls):
		captured = {}

		def _capture():
			captured["flag"] = frappe.flags.get(bulk_transfer.BULK_IMPORT_PROJECT_FLAG)

		mock_importer_cls.return_value.import_data.side_effect = _capture

		frappe.set_user(self.manager_user)
		bulk_transfer.import_records(self.project, "EGC Activity", "/files/whatever.csv")

		self.assertEqual(captured["flag"], self.project)
		self.assertFalse(frappe.flags.get(bulk_transfer.BULK_IMPORT_PROJECT_FLAG))

	@patch("frappe.core.doctype.data_import.importer.Importer")
	@patch("frappe.core.doctype.data_import.data_import.DataImport.get_importer", lambda self: _StubImporter())
	def test_project_flag_is_cleared_even_if_the_importer_raises(self, mock_importer_cls):
		mock_importer_cls.return_value.import_data.side_effect = RuntimeError("boom")

		frappe.set_user(self.manager_user)
		with self.assertRaises(RuntimeError):
			bulk_transfer.import_records(self.project, "EGC Activity", "/files/whatever.csv")

		self.assertFalse(frappe.flags.get(bulk_transfer.BULK_IMPORT_PROJECT_FLAG))

	# -- enforce_bulk_import_project: the actual security-critical logic ------------------------

	def test_new_row_is_force_scoped_to_the_import_project(self):
		other_project = _make_project(self.company)
		doc = frappe.new_doc("EGC Activity")
		doc.project = other_project
		doc.activity_code = "BULK-FORCE"
		doc.activity_name = "BULK-FORCE"

		frappe.flags[bulk_transfer.BULK_IMPORT_PROJECT_FLAG] = self.project
		bulk_transfer.enforce_bulk_import_project(doc)

		self.assertEqual(doc.project, self.project)

	def test_existing_row_in_a_different_project_is_rejected(self):
		activity = _make_activity(self.project, "BULK-XPROJ")
		doc = frappe.get_doc("EGC Activity", activity)

		other_project = _make_project(self.company)
		frappe.flags[bulk_transfer.BULK_IMPORT_PROJECT_FLAG] = other_project
		with self.assertRaises(frappe.ValidationError):
			bulk_transfer.enforce_bulk_import_project(doc)

	def test_existing_row_in_the_same_project_is_left_alone(self):
		activity = _make_activity(self.project, "BULK-SAMEPROJ")
		doc = frappe.get_doc("EGC Activity", activity)

		frappe.flags[bulk_transfer.BULK_IMPORT_PROJECT_FLAG] = self.project
		bulk_transfer.enforce_bulk_import_project(doc)  # must not raise

		self.assertEqual(doc.project, self.project)

	def test_is_a_no_op_outside_the_import_window(self):
		# No flag set — ordinary hand-typed record creation/editing must be completely unaffected.
		other_project = _make_project(self.company)
		doc = frappe.new_doc("EGC Activity")
		doc.project = other_project
		doc.activity_code = "BULK-NOFLAG"
		doc.activity_name = "BULK-NOFLAG"

		bulk_transfer.enforce_bulk_import_project(doc)

		self.assertEqual(doc.project, other_project)

	def test_a_real_import_cannot_reassign_an_existing_record_across_projects(self):
		# End-to-end version of the two checks above, through the doctype's own validate() chain
		# (hooks.py wiring), not just a direct call to the hook function.
		activity = _make_activity(self.project, "BULK-E2E-XPROJ")
		other_project = _make_project(self.company)

		frappe.flags[bulk_transfer.BULK_IMPORT_PROJECT_FLAG] = other_project
		try:
			doc = frappe.get_doc("EGC Activity", activity)
			with self.assertRaises(frappe.ValidationError):
				doc.save(ignore_permissions=True)
		finally:
			frappe.flags[bulk_transfer.BULK_IMPORT_PROJECT_FLAG] = None

		self.assertEqual(frappe.db.get_value("EGC Activity", activity, "project"), self.project)

	def test_a_real_import_force_scopes_a_new_record_through_validate(self):
		other_project = _make_project(self.company)
		frappe.flags[bulk_transfer.BULK_IMPORT_PROJECT_FLAG] = self.project
		try:
			doc = frappe.get_doc(
				{
					"doctype": "EGC Activity",
					"project": other_project,
					"activity_code": "BULK-E2E-FORCE",
					"activity_name": "BULK-E2E-FORCE",
				}
			)
			doc.insert(ignore_permissions=True)
		finally:
			frappe.flags[bulk_transfer.BULK_IMPORT_PROJECT_FLAG] = None

		self.assertEqual(frappe.db.get_value("EGC Activity", doc.name, "project"), self.project)

	# -- full round-trip: real export -> real file -> real Importer, nothing mocked -------------

	def test_export_then_import_round_trip_creates_a_real_record(self):
		frappe.set_user(self.manager_user)

		frappe.local.response = frappe._dict()
		bulk_transfer.get_export_template(self.project, "EGC WBS Node", "CSV", False)
		header_row = frappe.response["result"].splitlines()[0]
		columns = [c.strip('"') for c in header_row.split(",")]

		values = {
			"Project": self.project,
			"WBS Code": "RT.01",
			"WBS Name": "Round Trip Test Node",
			"Sequence": "1",
		}
		data_row = ",".join(f'"{values.get(col, "")}"' for col in columns)
		csv_content = f"{header_row}\n{data_row}\n"

		file_doc = frappe.get_doc(
			{"doctype": "File", "file_name": "roundtrip.csv", "is_private": 1, "content": csv_content.encode()}
		).insert(ignore_permissions=True)

		result = bulk_transfer.import_records(self.project, "EGC WBS Node", file_doc.file_url)

		self.assertEqual(result["success_count"], 1)
		self.assertEqual(result["failure_count"], 0)
		self.assertTrue(
			frappe.db.exists("EGC WBS Node", {"project": self.project, "wbs_code": "RT.01"})
		)


def _get_or_create_user(email, roles):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		)
		user.insert(ignore_permissions=True)
	user.add_roles(*roles)
	return user.name


def _make_project(company):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-Bulk-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_activity(project, code):
	doc = frappe.get_doc(
		{"doctype": "EGC Activity", "project": project, "activity_code": code, "activity_name": code}
	)
	doc.insert(ignore_permissions=True)
	return doc.name
