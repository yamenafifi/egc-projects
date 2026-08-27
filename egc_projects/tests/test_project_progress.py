# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for `project_progress.py` — `Project.percent_complete` synced from EGC Activity roots.

Regression coverage for a confirmed bug: core `Project.update_percent_complete()` resets
`percent_complete` to 0 on EVERY save when `percent_complete_method="Task Completion"` (the
field's own default) and there are zero core `Task` rows — which is always true for this app,
since it uses `EGC Activity` exclusively. A bare one-time `frappe.db.set_value` does not survive
the next save; these tests assert the fix survives repeated saves, not just one read.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from egc_projects.egc_projects import project_progress
from egc_projects.egc_projects.constants import ACTIVITY_COMPLETED, ACTIVITY_IN_PROGRESS


def _make_company() -> str:
	existing = frappe.db.get_value("Company", {}, "name")
	if existing:
		return existing
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "EGC Progress Test Co",
			"abbr": "EPTC",
			"default_currency": "USD",
			"country": "United Arab Emirates",
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def _make_project(**kwargs) -> str:
	values = {
		"doctype": "Project",
		"project_name": f"EGC-Progress-Test-{frappe.generate_hash(length=8)}",
		"company": _make_company(),
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_activity(project, code, **kwargs):
	values = {
		"doctype": "EGC Activity",
		"project": project,
		"activity_code": code,
		"activity_name": code,
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


class TestProjectProgress(IntegrationTestCase):
	def setUp(self):
		self.project = _make_project()

	# -- the core bug: survives repeated saves, not just one read --------------------------------

	def test_percent_complete_survives_repeated_project_saves(self):
		"""The regression this whole module exists to fix: a bare one-time write would be wiped
		out by core's own zero-reset on the NEXT save — assert it holds across several."""
		_make_activity(
			self.project, "PC-A", percent_complete=80, status=ACTIVITY_IN_PROGRESS, planned_start_date=today()
		)

		for _ in range(3):
			doc = frappe.get_doc("Project", self.project)
			doc.save()

		self.assertEqual(frappe.db.get_value("Project", self.project, "percent_complete"), 80)

	def test_project_with_zero_activities_and_zero_tasks_is_left_untouched(self):
		# Nothing to derive from — core's own zero-reset (the pre-existing, expected behaviour
		# for a genuinely empty project) is left alone, not overridden to something fabricated.
		doc = frappe.get_doc("Project", self.project)
		doc.save()
		self.assertEqual(frappe.db.get_value("Project", self.project, "percent_complete"), 0)

	# -- a project genuinely using core Task is never touched -----------------------------------

	def test_project_with_real_tasks_is_never_overridden(self):
		task = frappe.get_doc(
			{"doctype": "Task", "subject": "Real core task", "project": self.project, "status": "Open"}
		)
		task.insert(ignore_permissions=True)
		# Also give it Activities — if the safe-default check were wrong, this would prove it by
		# letting Activity data win over a project that's genuinely using core Task.
		_make_activity(
			self.project, "PC-B", percent_complete=50, status=ACTIVITY_IN_PROGRESS, planned_start_date=today()
		)

		doc = frappe.get_doc("Project", self.project)
		doc.save()

		# Core's own Task-based computation (0 of 1 tasks Completed/Cancelled) — not the
		# Activity-derived 50.
		self.assertEqual(frappe.db.get_value("Project", self.project, "percent_complete"), 0)

	# -- explicit opt-in via the new method value -------------------------------------------------

	def test_activity_completion_method_syncs_explicitly(self):
		doc = frappe.get_doc("Project", self.project)
		doc.percent_complete_method = project_progress.PERCENT_COMPLETE_METHOD
		doc.save()
		_make_activity(
			self.project, "PC-C", percent_complete=25, status=ACTIVITY_IN_PROGRESS, planned_start_date=today()
		)

		doc.reload()
		doc.save()
		self.assertEqual(frappe.db.get_value("Project", self.project, "percent_complete"), 25)

	# -- multiple root Activities: unweighted mean across roots ----------------------------------

	def test_multiple_roots_combine_as_unweighted_mean(self):
		_make_activity(
			self.project, "PC-ROOT-1", percent_complete=100, status=ACTIVITY_COMPLETED, planned_start_date=today()
		)
		_make_activity(
			self.project, "PC-ROOT-2", percent_complete=0, status="Not Started", planned_start_date=today()
		)

		doc = frappe.get_doc("Project", self.project)
		doc.save()
		self.assertEqual(frappe.db.get_value("Project", self.project, "percent_complete"), 50)

	# -- status auto-flip, mirroring core's own rule ----------------------------------------------

	def test_status_flips_to_completed_at_100_percent(self):
		_make_activity(self.project, "PC-D", percent_complete=100, status=ACTIVITY_COMPLETED)

		doc = frappe.get_doc("Project", self.project)
		doc.save()

		row = frappe.db.get_value("Project", self.project, ["percent_complete", "status"], as_dict=True)
		self.assertEqual(row.percent_complete, 100)
		self.assertEqual(row.status, "Completed")

	def test_on_hold_status_is_never_overridden(self):
		_make_activity(
			self.project, "PC-E", percent_complete=100, status=ACTIVITY_COMPLETED, planned_start_date=today()
		)

		doc = frappe.get_doc("Project", self.project)
		doc.status = "On hold"
		doc.save()

		row = frappe.db.get_value("Project", self.project, ["percent_complete", "status"], as_dict=True)
		# percent_complete still syncs from Activities; status is left alone, matching core's own
		# skip-Cancelled/On-hold rule in update_percent_complete().
		self.assertEqual(row.percent_complete, 100)
		self.assertEqual(row.status, "On hold")

	# -- reactive refresh: an Activity edit updates Project immediately, no separate save --------

	def test_activity_save_reactively_refreshes_project_percent_complete(self):
		doc = frappe.get_doc("Project", self.project)
		doc.percent_complete_method = project_progress.PERCENT_COMPLETE_METHOD
		doc.save()

		activity = _make_activity(
			self.project, "PC-F", percent_complete=10, status=ACTIVITY_IN_PROGRESS, planned_start_date=today()
		)
		self.assertEqual(frappe.db.get_value("Project", self.project, "percent_complete"), 10)

		activity.percent_complete = 90
		activity.save()
		# No Project.save() call at all here — this must already reflect the edit.
		self.assertEqual(frappe.db.get_value("Project", self.project, "percent_complete"), 90)

	# -- direct compute_percent_complete() contract -----------------------------------------------

	def test_compute_percent_complete_returns_none_for_no_roots(self):
		self.assertIsNone(project_progress.compute_percent_complete(self.project))
