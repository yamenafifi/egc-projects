# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for `schedule_engine.py` (Level 0 §27-§28): dependency-driven forecast-date
propagation. Baseline (`planned_start_date`/`planned_end_date`) and Actual dates are never
touched by this engine — only `forecast_start_date`/`forecast_end_date`, and only ever pushed
FORWARD, never pulled earlier.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from egc_projects.egc_projects import constants as c, schedule_engine


def _get_or_create_company():
	existing = frappe.db.get_value("Company", {}, "name")
	if existing:
		return existing
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "EGC Schedule Engine Test Co",
			"abbr": "ESETC",
			"default_currency": "USD",
			"country": "United Arab Emirates",
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def _make_project():
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-SchedEng-Test-{frappe.generate_hash(length=8)}",
			"company": _get_or_create_company(),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_activity(project, code, **kwargs):
	values = {
		"doctype": "EGC Activity",
		"project": project,
		"activity_code": code,
		"activity_name": kwargs.pop("activity_name", code),
	}
	values.update(kwargs)
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc


def _make_dependency(predecessor, successor, dependency_type=c.DEPENDENCY_FS, lag_days=0):
	doc = frappe.get_doc(
		{
			"doctype": "EGC Activity Dependency",
			"predecessor": predecessor,
			"successor": successor,
			"dependency_type": dependency_type,
			"lag_days": lag_days,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestScheduleEngine(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

	def setUp(self):
		self.project = _make_project()

	def test_fs_dependency_pushes_successor_forecast_forward(self):
		pred = _make_activity(
			self.project, "SE-A1", planned_start_date=today(), planned_end_date=add_days(today(), 5)
		)
		succ = _make_activity(self.project, "SE-A2")

		_make_dependency(pred.name, succ.name, c.DEPENDENCY_FS)

		succ.reload()
		self.assertEqual(getdate(succ.forecast_start_date), getdate(add_days(pred.planned_end_date, 1)))

	def test_ss_dependency_pushes_start_only(self):
		pred = _make_activity(
			self.project, "SE-B1", planned_start_date=today(), planned_end_date=add_days(today(), 5)
		)
		succ = _make_activity(
			self.project, "SE-B2", planned_start_date=today(), planned_end_date=add_days(today(), 2)
		)

		_make_dependency(pred.name, succ.name, c.DEPENDENCY_SS)

		succ.reload()
		self.assertEqual(getdate(succ.forecast_start_date), getdate(pred.planned_start_date))

	def test_ff_dependency_pushes_end_only(self):
		pred = _make_activity(
			self.project, "SE-C1", planned_start_date=today(), planned_end_date=add_days(today(), 10)
		)
		succ = _make_activity(
			self.project, "SE-C2", planned_start_date=today(), planned_end_date=add_days(today(), 2)
		)

		_make_dependency(pred.name, succ.name, c.DEPENDENCY_FF)

		succ.reload()
		self.assertEqual(getdate(succ.forecast_end_date), getdate(pred.planned_end_date))
		# FF constrains only the finish — the start this engine already knew about is untouched.
		self.assertIsNone(succ.forecast_start_date)

	def test_lag_days_delays_the_push(self):
		pred = _make_activity(
			self.project, "SE-D1", planned_start_date=today(), planned_end_date=add_days(today(), 5)
		)
		succ = _make_activity(self.project, "SE-D2")

		_make_dependency(pred.name, succ.name, c.DEPENDENCY_FS, lag_days=3)

		succ.reload()
		self.assertEqual(getdate(succ.forecast_start_date), getdate(add_days(pred.planned_end_date, 4)))

	def test_preserves_successor_duration_when_pushing_start(self):
		pred = _make_activity(
			self.project, "SE-E1", planned_start_date=today(), planned_end_date=add_days(today(), 5)
		)
		# A 4-day-long successor, scheduled well before the predecessor even starts.
		succ = _make_activity(
			self.project,
			"SE-E2",
			planned_start_date=add_days(today(), -10),
			planned_end_date=add_days(today(), -7),
		)

		_make_dependency(pred.name, succ.name, c.DEPENDENCY_FS)

		succ.reload()
		new_start = getdate(succ.forecast_start_date)
		new_end = getdate(succ.forecast_end_date)
		self.assertEqual(new_start, getdate(add_days(pred.planned_end_date, 1)))
		# Original span was 3 days (date_diff of -7 to -10) — preserved after the push.
		self.assertEqual((new_end - new_start).days, 3)

	def test_never_pulls_forecast_earlier(self):
		pred = _make_activity(
			self.project, "SE-F1", planned_start_date=today(), planned_end_date=add_days(today(), 5)
		)
		# Successor's own forecast is already well past what the dependency would require.
		succ = _make_activity(
			self.project,
			"SE-F2",
			planned_start_date=add_days(today(), 30),
			planned_end_date=add_days(today(), 35),
			forecast_start_date=add_days(today(), 30),
			forecast_end_date=add_days(today(), 35),
		)

		_make_dependency(pred.name, succ.name, c.DEPENDENCY_FS)

		succ.reload()
		self.assertEqual(getdate(succ.forecast_start_date), getdate(add_days(today(), 30)))

	def test_editing_predecessor_date_cascades_to_successor(self):
		pred = _make_activity(
			self.project, "SE-G1", planned_start_date=today(), planned_end_date=add_days(today(), 5)
		)
		succ = _make_activity(self.project, "SE-G2")
		_make_dependency(pred.name, succ.name, c.DEPENDENCY_FS)

		succ.reload()
		first_push = getdate(succ.forecast_start_date)

		pred.forecast_end_date = add_days(today(), 15)
		pred.save()

		succ.reload()
		self.assertGreater(getdate(succ.forecast_start_date), first_push)
		self.assertEqual(getdate(succ.forecast_start_date), getdate(add_days(pred.forecast_end_date, 1)))

	def test_multi_level_chain_cascades(self):
		a = _make_activity(self.project, "SE-H1", planned_start_date=today(), planned_end_date=add_days(today(), 5))
		# B needs a known duration of its own (a planned span) — otherwise, once A pushes only
		# B's start forward, B's own FINISH stays unknown and C (which depends on B finishing)
		# has nothing to anchor to. A real scheduling tool has the same requirement: an
		# undated activity has no duration to project forward from.
		b = _make_activity(
			self.project, "SE-H2", planned_start_date=today(), planned_end_date=add_days(today(), 2)
		)
		c_act = _make_activity(self.project, "SE-H3")
		_make_dependency(a.name, b.name, c.DEPENDENCY_FS)
		_make_dependency(b.name, c_act.name, c.DEPENDENCY_FS)

		b.reload()
		c_act.reload()
		self.assertIsNotNone(b.forecast_start_date)
		# C depends on B, whose forecast dates were only just set by the first cascade — the
		# second hop must have picked that up in the SAME propagation walk, not require a
		# separate manual trigger.
		self.assertIsNotNone(c_act.forecast_start_date)
		self.assertGreater(getdate(c_act.forecast_start_date), getdate(b.forecast_start_date))

	def test_group_successor_is_never_pushed(self):
		pred = _make_activity(
			self.project, "SE-I1", planned_start_date=today(), planned_end_date=add_days(today(), 5)
		)
		group = _make_activity(self.project, "SE-I2", is_group=1)

		_make_dependency(pred.name, group.name, c.DEPENDENCY_FS)

		group.reload()
		# A group's dates are rollup-owned by activity_control.py — the schedule engine must
		# leave them alone entirely, not race the rollup engine for the same fields.
		self.assertIsNone(group.forecast_start_date)

	def test_direct_edit_violating_dependency_is_rejected(self):
		pred = _make_activity(
			self.project, "SE-J1", planned_start_date=today(), planned_end_date=add_days(today(), 5)
		)
		succ = _make_activity(self.project, "SE-J2")
		_make_dependency(pred.name, succ.name, c.DEPENDENCY_FS)

		succ.reload()
		succ.forecast_start_date = today()  # before the predecessor even finishes
		with self.assertRaises(frappe.ValidationError):
			succ.save()

	def test_get_dependency_violations_empty_when_satisfied(self):
		pred = _make_activity(
			self.project, "SE-K1", planned_start_date=today(), planned_end_date=add_days(today(), 5)
		)
		succ = _make_activity(self.project, "SE-K2")
		_make_dependency(pred.name, succ.name, c.DEPENDENCY_FS)

		self.assertEqual(schedule_engine.get_dependency_violations(succ.name), [])
