"""Tests for Activity schedule depth and parent rollup (docs/ARCHITECTURE_V2.md §5).

Fixture style matches `test_activity.py`: one `Project` per test class, `make_activity` builds
a bare Activity via `.insert()` so every DocType-level validation actually runs.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from egc_projects.egc_projects import activity_control
from egc_projects.egc_projects.constants import (
	ACTIVITY_CANCELLED,
	ACTIVITY_COMPLETED,
	ACTIVITY_IN_PROGRESS,
	ACTIVITY_NOT_STARTED,
)


def get_test_company() -> str:
	existing = frappe.db.get_value("Company", {}, "name")
	if existing:
		return existing
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "EGC Activity Schedule Test Co",
			"abbr": "EASC",
			"default_currency": "USD",
			"country": "United Arab Emirates",
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def make_project(project_name: str) -> str:
	project = frappe.get_doc(
		{"doctype": "Project", "project_name": project_name, "company": get_test_company(), "status": "Open"}
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


class TestActivitySchedule(IntegrationTestCase):
	def setUp(self):
		suffix = frappe.generate_hash(length=6)
		self.project = make_project(f"EGC Activity Schedule Test {suffix}")

	# -- duration_days ------------------------------------------------------------------------

	def test_duration_days_computed_for_leaf(self):
		leaf = make_activity(
			self.project,
			"DUR-1",
			"Leaf",
			planned_start_date=today(),
			planned_end_date=add_days(today(), 9),
		)
		self.assertEqual(leaf.duration_days, 10)

	def test_duration_days_zero_when_dates_missing(self):
		# `duration_days` is an Int field, whose DB column is NOT NULL DEFAULT 0 in Frappe;
		# a formula that always produces >= 1 for real dates makes 0 an unambiguous "unset"
		# marker (see activity_control.py's `_duration` docstring).
		leaf = make_activity(self.project, "DUR-2", "Leaf No Dates")
		self.assertEqual(leaf.duration_days, 0)

		leaf_only_start = make_activity(self.project, "DUR-3", "Leaf Start Only", planned_start_date=today())
		self.assertEqual(leaf_only_start.duration_days, 0)

	# -- parent rollup --------------------------------------------------------------------------

	def _build_three_level_tree(self):
		"""Ductwork (group) > Installation (group) > {MRI-01, MRI-02} (leaves)."""
		ductwork = make_activity(self.project, "DUCT", "Ductwork", is_group=1)
		installation = make_activity(
			self.project, "DUCT-INS", "Installation", is_group=1, parent_egc_activity=ductwork.name
		)
		mri1 = make_activity(
			self.project,
			"DUCT-INS-M1",
			"MRI-01",
			parent_egc_activity=installation.name,
			planned_start_date=today(),
			planned_end_date=add_days(today(), 4),
			percent_complete=40,
			status=ACTIVITY_IN_PROGRESS,
		)
		mri2 = make_activity(
			self.project,
			"DUCT-INS-M2",
			"MRI-02",
			parent_egc_activity=installation.name,
			planned_start_date=add_days(today(), 2),
			planned_end_date=add_days(today(), 10),
			percent_complete=60,
			status=ACTIVITY_IN_PROGRESS,
		)
		return ductwork, installation, mri1, mri2

	def test_rollup_percent_and_dates_propagate_to_grandparent(self):
		ductwork, installation, mri1, mri2 = self._build_three_level_tree()

		installation.reload()
		self.assertEqual(installation.percent_complete, 50)  # average of 40 and 60
		self.assertEqual(str(installation.planned_start_date), str(today()))
		self.assertEqual(str(installation.planned_end_date), str(add_days(today(), 10)))
		self.assertEqual(installation.duration_days, 11)

		# The grandparent must reflect Installation's ALREADY-ROLLED-UP values, not recompute
		# from leaves directly — proves refresh_ancestors visits bottom-up in one pass.
		ductwork.reload()
		self.assertEqual(ductwork.percent_complete, 50)
		self.assertEqual(str(ductwork.planned_start_date), str(today()))
		self.assertEqual(str(ductwork.planned_end_date), str(add_days(today(), 10)))

	def test_rollup_status_all_completed(self):
		ductwork, installation, mri1, mri2 = self._build_three_level_tree()
		mri1.status = ACTIVITY_COMPLETED
		mri1.percent_complete = 100
		mri1.save()
		mri2.status = ACTIVITY_COMPLETED
		mri2.percent_complete = 100
		mri2.save()

		installation.reload()
		self.assertEqual(installation.status, ACTIVITY_COMPLETED)
		self.assertEqual(installation.percent_complete, 100)

	def test_rollup_status_all_not_started(self):
		ductwork = make_activity(self.project, "NS-GRP", "Not Started Group", is_group=1)
		make_activity(self.project, "NS-A", "A", parent_egc_activity=ductwork.name)
		make_activity(self.project, "NS-B", "B", parent_egc_activity=ductwork.name)

		ductwork.reload()
		self.assertEqual(ductwork.status, ACTIVITY_NOT_STARTED)

	def test_rollup_excludes_cancelled_children(self):
		ductwork, installation, mri1, mri2 = self._build_three_level_tree()
		# Both children Completed except one is Cancelled — Cancelled must not force the
		# parent's status either way; the surviving live child alone decides it.
		mri1.status = ACTIVITY_COMPLETED
		mri1.percent_complete = 100
		mri1.save()
		mri2.status = ACTIVITY_CANCELLED
		mri2.save()

		installation.reload()
		self.assertEqual(installation.status, ACTIVITY_COMPLETED)

	def test_rollup_actual_end_date_only_when_every_child_has_one(self):
		ductwork, installation, mri1, mri2 = self._build_three_level_tree()
		mri1.actual_end_date = today()
		mri1.save()

		installation.reload()
		self.assertFalse(installation.actual_end_date)  # mri2 has none yet — Date field, stays null/falsy

		mri2.actual_end_date = add_days(today(), 1)
		mri2.save()

		installation.reload()
		self.assertEqual(str(installation.actual_end_date), str(add_days(today(), 1)))

	def test_group_rollup_fields_cannot_be_hand_edited(self):
		ductwork, installation, mri1, mri2 = self._build_three_level_tree()

		installation.reload()
		installation.percent_complete = 99
		with self.assertRaises(frappe.ValidationError):
			installation.save()

	def test_new_group_with_no_children_keeps_its_initial_values(self):
		# Nothing to roll up from yet — the engine must not reset a fresh group to blank/zero.
		group = make_activity(self.project, "EMPTY-GRP", "Empty Group", is_group=1, percent_complete=0)
		self.assertEqual(group.percent_complete, 0)
		activity_control.refresh_activity_rollup(group.name)
		group.reload()
		self.assertEqual(group.percent_complete, 0)

	def test_editing_leaf_propagates_up_entire_ancestor_chain(self):
		ductwork, installation, mri1, mri2 = self._build_three_level_tree()
		mri1.percent_complete = 100
		mri1.status = ACTIVITY_COMPLETED
		mri1.save()

		installation.reload()
		ductwork.reload()
		expected = (100 + 60) / 2
		self.assertEqual(installation.percent_complete, expected)
		self.assertEqual(ductwork.percent_complete, expected)
