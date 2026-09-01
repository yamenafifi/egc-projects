# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Regression coverage for `project_files.py` — the per-project `Home/Projects/<project>/
{Documents,Drawings,Submittals,Photos}` folder structure. New uploads only; already-uploaded
files are never migrated (see docs/ARCHITECTURE.md)."""

import frappe
from frappe.tests import IntegrationTestCase

from egc_projects import install
from egc_projects.egc_projects import project_files


def _make_project():
	company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
	return frappe.get_doc(
		{"doctype": "Project", "project_name": f"EGC-Folders-Test-{frappe.generate_hash(length=8)}", "company": company}
	).insert(ignore_permissions=True).name


class TestEnsureProjectFolders(IntegrationTestCase):
	def test_creates_exactly_the_expected_subfolders(self):
		project = _make_project()

		for subfolder in project_files.PROJECT_SUBFOLDERS:
			name = project_files.project_folder_path(project, subfolder)
			self.assertTrue(frappe.db.exists("File", name), name)
			self.assertEqual(frappe.db.get_value("File", name, "is_folder"), 1)

	def test_is_idempotent(self):
		project = _make_project()
		before = frappe.db.count("File", {"folder": ("like", f"Home/Projects/{project}%")})

		project_files.ensure_project_folders(project)
		project_files.ensure_project_folders(project)

		after = frappe.db.count("File", {"folder": ("like", f"Home/Projects/{project}%")})
		self.assertEqual(before, after)

	def test_blank_project_is_a_safe_no_op(self):
		project_files.ensure_project_folders("")
		project_files.ensure_project_folders(None)


class TestProvisionProjectFoldersHook(IntegrationTestCase):
	def test_after_insert_hook_provisions_folders_with_no_explicit_call(self):
		# `_make_project()`'s own `.insert()` is what fires `Project.after_insert` — no call to
		# `ensure_project_folders` anywhere in this test.
		project = _make_project()

		for subfolder in project_files.PROJECT_SUBFOLDERS:
			self.assertTrue(frappe.db.exists("File", project_files.project_folder_path(project, subfolder)))


class TestProvisionAllProjectFolders(IntegrationTestCase):
	def test_backfills_a_project_whose_folders_were_removed(self):
		project = _make_project()
		for subfolder in project_files.PROJECT_SUBFOLDERS:
			frappe.delete_doc("File", project_files.project_folder_path(project, subfolder), force=True)
			self.assertFalse(frappe.db.exists("File", project_files.project_folder_path(project, subfolder)))

		install.provision_all_project_folders()

		for subfolder in project_files.PROJECT_SUBFOLDERS:
			self.assertTrue(frappe.db.exists("File", project_files.project_folder_path(project, subfolder)))

	def test_is_safe_to_run_again_when_already_provisioned(self):
		_make_project()

		install.provision_all_project_folders()
		install.provision_all_project_folders()  # must not raise
