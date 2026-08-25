"""Tests for `EGC Activity` — docs/ARCHITECTURE.md §2.3.

Every test builds its own `Project` fixture (and, where the tree matters, its own subtree);
nothing here depends on data already present on the site.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from egc_projects.egc_projects.constants import (
	ACTIVITY_CANCELLED,
	ACTIVITY_COMPLETED,
	ACTIVITY_IN_PROGRESS,
	ACTIVITY_NOT_STARTED,
	ACTIVITY_ON_HOLD,
)
from egc_projects.egc_projects.doctype.egc_activity.egc_activity import get_children, is_overdue


def get_test_company() -> str:
	existing = frappe.db.get_value("Company", {}, "name")
	if existing:
		return existing

	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "EGC Activity Test Co",
			"abbr": "EATC",
			"default_currency": "USD",
			"country": "United Arab Emirates",
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def make_project(project_name: str) -> str:
	project = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": project_name,
			"company": get_test_company(),
			"status": "Open",
		}
	)
	project.insert(ignore_permissions=True)
	return project.name


def make_activity(project, activity_code, activity_name, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "EGC Activity",
			"project": project,
			"activity_code": activity_code,
			"activity_name": activity_name,
			**kwargs,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestEGCActivity(IntegrationTestCase):
	def setUp(self):
		suffix = frappe.generate_hash(length=6)
		self.project_a = make_project(f"EGC Activity Test A {suffix}")
		self.project_b = make_project(f"EGC Activity Test B {suffix}")

	def test_recursive_tree_builds_and_nests(self):
		# HVAC Ductwork > {Fabrication, Installation > {MRI-01, MRI-02}, Testing} — the same
		# DocType at every level, per docs/ARCHITECTURE.md §2.3.
		root = make_activity(self.project_a, "DUCT", "HVAC Ductwork", is_group=1)
		fab = make_activity(self.project_a, "DUCT-FAB", "Fabrication", parent_egc_activity=root.name)
		install = make_activity(
			self.project_a, "DUCT-INS", "Installation", is_group=1, parent_egc_activity=root.name
		)
		mri1 = make_activity(
			self.project_a, "DUCT-INS-MRI01", "MRI-01", parent_egc_activity=install.name
		)
		mri2 = make_activity(
			self.project_a, "DUCT-INS-MRI02", "MRI-02", parent_egc_activity=install.name
		)
		testing = make_activity(self.project_a, "DUCT-TST", "Testing", parent_egc_activity=root.name)

		for doc in (root, fab, install, mri1, mri2, testing):
			doc.reload()

		self.assertTrue(root.lft < fab.lft < fab.rgt < root.rgt)
		self.assertTrue(root.lft < install.lft < install.rgt < root.rgt)
		self.assertTrue(install.lft < mri1.lft < mri1.rgt < install.rgt)
		self.assertTrue(install.lft < mri2.lft < mri2.rgt < install.rgt)
		self.assertTrue(root.lft < testing.lft < testing.rgt < root.rgt)
		for doc in (root, fab, install, mri1, mri2, testing):
			self.assertEqual(doc.doctype, "EGC Activity")

	def test_cross_project_parent_rejected(self):
		group_b = make_activity(self.project_b, "GRP", "Group B", is_group=1)
		activity = frappe.get_doc(
			{
				"doctype": "EGC Activity",
				"project": self.project_a,
				"activity_code": "X1",
				"activity_name": "Cross Project Child",
				"parent_egc_activity": group_b.name,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			activity.insert(ignore_permissions=True)

	def test_cross_project_wbs_node_rejected(self):
		wbs_node = self._make_wbs_node_or_skip(self.project_b, "WBS-B", "WBS in B")
		activity = frappe.get_doc(
			{
				"doctype": "EGC Activity",
				"project": self.project_a,
				"activity_code": "X2",
				"activity_name": "Cross Project WBS",
				"wbs_node": wbs_node,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			activity.insert(ignore_permissions=True)

	def test_duplicate_activity_code_in_project_rejected(self):
		make_activity(self.project_a, "DUP", "First")
		with self.assertRaises(frappe.DuplicateEntryError):
			make_activity(self.project_a, "DUP", "Second")

	def test_same_code_in_different_project_accepted(self):
		make_activity(self.project_a, "SAME", "In A")
		doc = make_activity(self.project_b, "SAME", "In B")
		self.assertEqual(doc.activity_code, "SAME")

	def test_planned_end_before_start_rejected(self):
		activity = frappe.get_doc(
			{
				"doctype": "EGC Activity",
				"project": self.project_a,
				"activity_code": "DATES",
				"activity_name": "Bad Dates",
				"planned_start_date": today(),
				"planned_end_date": add_days(today(), -5),
			}
		)
		with self.assertRaises(frappe.exceptions.InvalidDates):
			activity.insert(ignore_permissions=True)

	def test_status_percent_consistency(self):
		completed = make_activity(
			self.project_a, "ST-DONE", "Done", status=ACTIVITY_COMPLETED, percent_complete=40
		)
		self.assertEqual(completed.percent_complete, 100)

		not_started = make_activity(
			self.project_a, "ST-NEW", "New", status=ACTIVITY_NOT_STARTED, percent_complete=40
		)
		self.assertEqual(not_started.percent_complete, 0)

		clamped_high = make_activity(
			self.project_a, "ST-WIP", "WIP", status=ACTIVITY_IN_PROGRESS, percent_complete=150
		)
		self.assertEqual(clamped_high.percent_complete, 100)

		clamped_low = make_activity(
			self.project_a, "ST-NEG", "Neg", status=ACTIVITY_ON_HOLD, percent_complete=-10
		)
		self.assertEqual(clamped_low.percent_complete, 0)

		# 100% while still "In Progress" is a contradiction only for the two terminal statuses;
		# the status itself is left for the user to change.
		full_but_wip = make_activity(
			self.project_a, "ST-FULL", "Full but WIP", status=ACTIVITY_IN_PROGRESS, percent_complete=100
		)
		self.assertEqual(full_but_wip.status, ACTIVITY_IN_PROGRESS)
		self.assertEqual(full_but_wip.percent_complete, 100)

	def test_is_overdue(self):
		self.assertTrue(is_overdue(ACTIVITY_IN_PROGRESS, add_days(today(), -1)))
		self.assertFalse(is_overdue(ACTIVITY_IN_PROGRESS, add_days(today(), 1)))
		self.assertFalse(is_overdue(ACTIVITY_IN_PROGRESS, None))
		self.assertFalse(is_overdue(ACTIVITY_COMPLETED, add_days(today(), -30)))
		self.assertFalse(is_overdue(ACTIVITY_CANCELLED, add_days(today(), -30)))
		self.assertTrue(is_overdue(ACTIVITY_ON_HOLD, add_days(today(), -1)))

	def test_get_children_scopes_to_project(self):
		make_activity(self.project_a, "GC-A1", "A1")
		make_activity(self.project_a, "GC-A2", "A2")
		make_activity(self.project_b, "GC-B1", "B1")

		frappe.set_user("Administrator")
		result = get_children("EGC Activity", project=self.project_a, is_root=True)

		returned_names = {row["value"] for row in result}
		names_in_a = set(
			frappe.get_all("EGC Activity", filters={"project": self.project_a}, pluck="name")
		)
		names_in_b = set(
			frappe.get_all("EGC Activity", filters={"project": self.project_b}, pluck="name")
		)

		self.assertTrue(returned_names.issubset(names_in_a))
		self.assertFalse(returned_names & names_in_b)
		for row in result:
			self.assertEqual(
				frappe.db.get_value("EGC Activity", row["value"], "project"), self.project_a
			)

	def _make_wbs_node_or_skip(self, project, wbs_code, wbs_name):
		if not frappe.db.exists("DocType", "EGC WBS Node"):
			self.skipTest(
				"EGC WBS Node DocType does not exist yet (built by a concurrent work package)."
			)
		doc = frappe.get_doc(
			{
				"doctype": "EGC WBS Node",
				"project": project,
				"wbs_code": wbs_code,
				"wbs_name": wbs_name,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
