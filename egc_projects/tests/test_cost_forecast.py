# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for `api/hub.py`'s `get_cost_forecast` — Earned Value Management using the
Activity-weighted `Project.percent_complete` as physical % complete. Sets Project's own
aggregate cost fields directly (`frappe.db.set_value`) rather than building real Purchase
Invoice/Timesheet/Expense Claim fixtures — `get_cost_forecast` reads straight off those stored
fields (same discipline as `get_financials`), so a controlled direct write exercises the actual
formula without the weight of `test_financial_transactions.py`'s real-transaction reconciliation
style, which is answering a different question (does the drill-down match the aggregate).
"""

import frappe
from frappe.permissions import add_user_permission
from frappe.tests import IntegrationTestCase

from egc_projects.api import hub
from egc_projects.egc_projects import constants as c


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


def _make_project(company, **field_values):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-CostForecast-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	if field_values:
		frappe.db.set_value("Project", doc.name, field_values, update_modified=False)
	return doc.name


class TestCostForecast(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]
		cls.manager_user = _get_or_create_user(
			"egc-cf-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		cls.viewer_user = _get_or_create_user("egc-cf-viewer@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER])
		cls.fenced_user = _get_or_create_user(
			"egc-cf-fenced@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_zero_budget_and_zero_spend_is_all_zero(self):
		project = _make_project(self.company)
		result = hub.get_cost_forecast(project)
		self.assertEqual(result["budget"], 0)
		self.assertEqual(result["actual_cost"], 0)
		self.assertEqual(result["earned_value"], 0)
		self.assertIsNone(result["cost_performance_index"])
		self.assertEqual(result["estimate_at_completion"], 0)
		self.assertEqual(result["estimate_to_complete"], 0)

	def test_nothing_spent_yet_remaining_equals_full_budget(self):
		project = _make_project(self.company, estimated_costing=100000, percent_complete=30)
		result = hub.get_cost_forecast(project)
		self.assertEqual(result["budget"], 100000)
		self.assertEqual(result["earned_value"], 30000)
		self.assertIsNone(result["cost_performance_index"])
		self.assertEqual(result["estimate_at_completion"], 100000)
		self.assertEqual(result["estimate_to_complete"], 100000)

	def test_on_budget_spending_forecasts_no_overrun(self):
		# 50% physically complete, and exactly 50% of budget spent to get there -> CPI 1.0,
		# forecast total cost stays at budget, remaining is simply the other half.
		project = _make_project(
			self.company, estimated_costing=200000, percent_complete=50, total_purchase_cost=100000
		)
		result = hub.get_cost_forecast(project)
		self.assertEqual(result["earned_value"], 100000)
		self.assertEqual(result["actual_cost"], 100000)
		self.assertAlmostEqual(result["cost_performance_index"], 1.0)
		self.assertAlmostEqual(result["estimate_at_completion"], 200000)
		self.assertAlmostEqual(result["estimate_to_complete"], 100000)

	def test_overspending_relative_to_progress_forecasts_overrun(self):
		# Only 25% physically complete but already spent HALF the budget getting there ->
		# CPI 0.5 (inefficient), so the forecast total cost should exceed the original budget.
		project = _make_project(
			self.company, estimated_costing=200000, percent_complete=25, total_purchase_cost=100000
		)
		result = hub.get_cost_forecast(project)
		self.assertEqual(result["earned_value"], 50000)
		self.assertAlmostEqual(result["cost_performance_index"], 0.5)
		self.assertAlmostEqual(result["estimate_at_completion"], 400000)
		self.assertAlmostEqual(result["estimate_to_complete"], 300000)

	def test_underspending_relative_to_progress_forecasts_savings(self):
		# 50% physically complete but only spent a QUARTER of the budget -> CPI 2.0 (efficient),
		# forecast total cost comes in under the original budget.
		project = _make_project(
			self.company, estimated_costing=200000, percent_complete=50, total_purchase_cost=50000
		)
		result = hub.get_cost_forecast(project)
		self.assertAlmostEqual(result["cost_performance_index"], 2.0)
		self.assertAlmostEqual(result["estimate_at_completion"], 100000)
		self.assertAlmostEqual(result["estimate_to_complete"], 50000)

	def test_actual_cost_sums_every_cost_side_field(self):
		project = _make_project(
			self.company,
			estimated_costing=100000,
			percent_complete=10,
			total_purchase_cost=1000,
			total_consumed_material_cost=2000,
			total_costing_amount=3000,
		)
		result = hub.get_cost_forecast(project)
		self.assertEqual(result["actual_cost"], 6000)

	# -- gates ------------------------------------------------------------------------------

	def test_financial_gate_denies_viewer_and_allows_manager(self):
		project = _make_project(self.company, estimated_costing=10000)

		frappe.set_user(self.viewer_user)
		with self.assertRaises(frappe.PermissionError):
			hub.get_cost_forecast(project)

		frappe.set_user(self.manager_user)
		hub.get_cost_forecast(project)  # must not raise

	def test_project_isolation(self):
		project = _make_project(self.company, estimated_costing=10000)
		# fenced_user has the Manager role but no permission on THIS specific project
		add_user_permission("Project", _make_project(self.company), self.fenced_user, ignore_permissions=True)

		frappe.set_user(self.fenced_user)
		with self.assertRaises(frappe.PermissionError):
			hub.get_cost_forecast(project)
