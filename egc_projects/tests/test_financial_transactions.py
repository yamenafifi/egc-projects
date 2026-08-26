# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for `api/hub.py`'s `get_financial_transactions` (docs/ARCHITECTURE_V2.md §10).

Each drill-down helper is a hand-reconstruction of the exact query ERPNext/HRMS uses to arrive
at the corresponding `get_financials()` figure. Rather than building full Sales/Purchase
Invoice/Expense Claim/Stock Entry/Timesheet fixtures here (heavy: tax templates, warehouses,
GL accounts), the reconciliation tests below read the REAL transactional data already present
on this dev site's seeded demo projects and assert the drill-down sums to the project's own
stored aggregate field — the same proof the architecture doc promises ("the drill-down and the
headline figure can never disagree"), without re-deriving the total independently. Each is
skipped if no project with a non-zero figure exists, so the suite stays green on a bare site.
"""

import frappe
from frappe.permissions import add_user_permission
from frappe.tests import IntegrationTestCase

from egc_projects.api import hub
from egc_projects.egc_projects import constants as c


def _first_project_with(fieldname):
	rows = frappe.get_all("Project", filters=[[fieldname, ">", 0]], fields=["name", fieldname], limit=1)
	return rows[0] if rows else None


class TestFinancialTransactions(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]
		cls.decoy_project = _make_project(cls.company)

		cls.manager_user = _get_or_create_user(
			"egc-fintx-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		cls.financial_denied_user = _get_or_create_user(
			"egc-fintx-viewer@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER]
		)
		cls.project_denied_user = _get_or_create_user(
			"egc-fintx-fenced@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		add_user_permission("Project", cls.decoy_project, cls.project_denied_user, ignore_permissions=True)

	def setUp(self):
		self.project = _make_project(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")

	# -- gate + validation -------------------------------------------------------------------

	def test_invalid_metric_rejected(self):
		frappe.set_user(self.manager_user)
		with self.assertRaises(frappe.ValidationError):
			hub.get_financial_transactions(self.project, "gross_margin")
		with self.assertRaises(frappe.ValidationError):
			hub.get_financial_transactions(self.project, "not_a_real_metric")

	def test_financial_gate_denies_viewer_and_allows_manager(self):
		frappe.set_user(self.financial_denied_user)
		with self.assertRaises(frappe.PermissionError):
			hub.get_financial_transactions(self.project, "billed")

		frappe.set_user(self.manager_user)
		hub.get_financial_transactions(self.project, "billed")  # must not raise

	def test_project_isolation(self):
		frappe.set_user(self.project_denied_user)
		with self.assertRaises(frappe.PermissionError):
			hub.get_financial_transactions(self.project, "billed")

	# -- reconciliation against real seeded transactions --------------------------------------

	def test_billed_transactions_sum_matches_project_total(self):
		row = _first_project_with("total_billed_amount")
		if not row:
			self.skipTest("No seeded project with a non-zero total_billed_amount on this site.")
		rows = hub.get_financial_transactions(row.name, "billed")
		self.assertTrue(all(r["doctype"] == "Sales Invoice" for r in rows))
		self.assertAlmostEqual(sum(r["amount"] for r in rows), row.total_billed_amount, places=2)

	def test_purchase_cost_transactions_sum_matches_project_total(self):
		row = _first_project_with("total_purchase_cost")
		if not row:
			self.skipTest("No seeded project with a non-zero total_purchase_cost on this site.")
		rows = hub.get_financial_transactions(row.name, "purchase_cost")
		self.assertTrue(all(r["doctype"] == "Purchase Invoice" for r in rows))
		self.assertAlmostEqual(sum(r["amount"] for r in rows), row.total_purchase_cost, places=2)

	def test_sales_order_transactions_sum_matches_project_total(self):
		row = _first_project_with("total_sales_amount")
		if not row:
			self.skipTest("No seeded project with a non-zero total_sales_amount on this site.")
		rows = hub.get_financial_transactions(row.name, "sales_order_value")
		self.assertTrue(all(r["doctype"] == "Sales Order" for r in rows))
		self.assertAlmostEqual(sum(r["amount"] for r in rows), row.total_sales_amount, places=2)

	def test_timesheet_transactions_sum_matches_project_total(self):
		row = _first_project_with("total_costing_amount")
		if not row:
			self.skipTest("No seeded project with a non-zero total_costing_amount on this site.")
		rows = hub.get_financial_transactions(row.name, "timesheet_cost")
		self.assertTrue(all(r["doctype"] == "Timesheet" for r in rows))
		self.assertAlmostEqual(sum(r["amount"] for r in rows), row.total_costing_amount, places=2)

	def test_expense_claim_transactions_sum_matches_project_total(self):
		row = _first_project_with("total_expense_claim")
		if not row:
			self.skipTest("No seeded project with a non-zero total_expense_claim on this site.")
		rows = hub.get_financial_transactions(row.name, "expense_claims")
		self.assertTrue(all(r["doctype"] == "Expense Claim" for r in rows))
		self.assertAlmostEqual(sum(r["amount"] for r in rows), row.total_expense_claim, places=2)

	def test_consumed_material_transactions_sum_matches_project_total(self):
		row = _first_project_with("total_consumed_material_cost")
		if not row:
			self.skipTest("No seeded project with a non-zero total_consumed_material_cost on this site.")
		rows = hub.get_financial_transactions(row.name, "consumed_material_cost")
		self.assertTrue(all(r["doctype"] == "Stock Entry" for r in rows))
		self.assertAlmostEqual(sum(r["amount"] for r in rows), row.total_consumed_material_cost, places=2)

	# -- empty case ----------------------------------------------------------------------------

	def test_no_transactions_returns_empty_list(self):
		frappe.set_user(self.manager_user)
		for metric in (
			"billed",
			"purchase_cost",
			"expense_claims",
			"consumed_material_cost",
			"timesheet_cost",
			"sales_order_value",
		):
			with self.subTest(metric=metric):
				self.assertEqual(hub.get_financial_transactions(self.project, metric), [])


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
			"project_name": f"EGC-FINTX-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name
