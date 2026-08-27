# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for `EGC Change Order` (the doctype itself) and `api/change_orders.py`'s
`get_contract_value_breakdown` — Option C from the Round 3 design discussion: this doctype owns
the approval process, the linked Sales Order owns the number. Submitting a Change Order IS the
approval step (docstatus 1); the breakdown endpoint must always reconcile Total = Original Scope
+ Change Orders, since both sides partition the exact same set of submitted Sales Orders core's
own `Project.update_sales_amount()` sums.

Builds real, submittable Sales Orders (not mocks) against this dev site's existing seeded
Customer/Item/Price List — see `test_financial_transactions.py`'s own docstring for why the
sibling suite avoids this weight in general; Change Order logic specifically hinges on wrapping
particular Sales Orders, so a real fixture is unavoidable here.
"""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from egc_projects.api import change_orders
from egc_projects.egc_projects import constants as c

_ITEM_CODE = "خدمات"
_CUSTOMER = "C00003"


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


class TestChangeOrders(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = frappe.db.get_value("Sales Order", {"docstatus": 1}, "company")
		if not cls.company:
			raise unittest.SkipTest("No submitted Sales Order exists on this site to model a company from.")

		cls.manager_user = _get_or_create_user(
			"egc-co-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		cls.viewer_user = _get_or_create_user(
			"egc-co-viewer@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER]
		)

	def setUp(self):
		frappe.set_user("Administrator")
		self.project = _make_project(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _make_so(self, amount, project=None, submit=True):
		return _make_sales_order(project or self.project, self.company, amount, submit=submit)

	def _make_co(self, sales_order, co_number="CO-001", project=None, submit=False):
		doc = frappe.get_doc(
			{
				"doctype": "EGC Change Order",
				"project": project or self.project,
				"co_number": co_number,
				"title": "Additional scope",
				"sales_order": sales_order,
			}
		)
		doc.insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc

	# -- doctype validation -----------------------------------------------------------------

	def test_amount_is_synced_from_sales_order_not_settable_directly(self):
		so = self._make_so(50000)
		doc = self._make_co(so)
		self.assertEqual(doc.amount, 50000)

		doc.amount = 999999
		doc.save()
		self.assertEqual(doc.amount, 50000)

	def test_sales_order_must_be_submitted(self):
		so = self._make_so(10000, submit=False)
		with self.assertRaises(frappe.ValidationError):
			self._make_co(so)

	def test_sales_order_from_another_project_rejected(self):
		other_project = _make_project(self.company)
		so = self._make_so(10000, project=other_project)
		with self.assertRaises(frappe.ValidationError):
			self._make_co(so)

	def test_co_number_unique_per_project(self):
		so1 = self._make_so(10000)
		so2 = self._make_so(20000)
		self._make_co(so1, co_number="CO-DUP")
		with self.assertRaises(frappe.ValidationError):
			self._make_co(so2, co_number="CO-DUP")

	def test_sales_order_cannot_be_wrapped_by_two_active_change_orders(self):
		so = self._make_so(10000)
		self._make_co(so, co_number="CO-A")
		with self.assertRaises(frappe.ValidationError):
			self._make_co(so, co_number="CO-B")

	def test_submit_sets_approval_date_and_approved_by(self):
		so = self._make_so(10000)
		doc = self._make_co(so, submit=True)
		self.assertEqual(doc.approval_date, today())
		self.assertEqual(doc.approved_by, "Administrator")

	def test_cancelled_change_order_frees_its_sales_order_for_reuse(self):
		# Regression: a DB-level unique constraint on `sales_order` would block this, since the
		# cancelled document still physically occupies the value in the table (this doctype has
		# no `amended_from` field, matching every other submittable doctype in this app — the
		# correction path is cancel-and-recreate, not the Desk "Amend" button).
		so = self._make_so(10000)
		doc = self._make_co(so, co_number="CO-ORIGINAL", submit=True)
		doc.cancel()

		replacement = self._make_co(so, co_number="CO-REPLACEMENT", submit=True)
		self.assertEqual(replacement.sales_order, so)
		self.assertEqual(replacement.docstatus, 1)

	# -- get_contract_value_breakdown ---------------------------------------------------------

	def test_breakdown_with_no_sales_orders_is_all_zero(self):
		result = change_orders.get_contract_value_breakdown(self.project)
		self.assertEqual(result["total"], 0)
		self.assertEqual(result["original_scope_total"], 0)
		self.assertEqual(result["change_orders_total"], 0)

	def test_breakdown_with_no_change_orders_is_entirely_original_scope(self):
		self._make_so(30000)
		self._make_so(20000)
		result = change_orders.get_contract_value_breakdown(self.project)
		self.assertEqual(result["total"], 50000)
		self.assertEqual(result["original_scope_total"], 50000)
		self.assertEqual(result["change_orders_total"], 0)

	def test_breakdown_splits_original_scope_and_change_orders(self):
		original_so = self._make_so(100000)
		co_so = self._make_so(25000)
		self._make_co(co_so, submit=True)

		result = change_orders.get_contract_value_breakdown(self.project)
		self.assertEqual(result["total"], 125000)
		self.assertEqual(result["original_scope_total"], 100000)
		self.assertEqual(result["change_orders_total"], 25000)
		self.assertEqual(len(result["change_orders"]), 1)
		self.assertEqual(result["change_orders"][0]["sales_order"], co_so)

	def test_draft_change_order_does_not_count_toward_change_orders_total(self):
		# Only a SUBMITTED (approved) Change Order moves its Sales Order out of Original Scope —
		# a Draft is still being prepared, not yet approved.
		so = self._make_so(40000)
		self._make_co(so, submit=False)

		result = change_orders.get_contract_value_breakdown(self.project)
		self.assertEqual(result["total"], 40000)
		self.assertEqual(result["original_scope_total"], 40000)
		self.assertEqual(result["change_orders_total"], 0)

	def test_cancelled_change_order_returns_sales_order_to_original_scope(self):
		so = self._make_so(15000)
		doc = self._make_co(so, submit=True)
		doc.cancel()

		result = change_orders.get_contract_value_breakdown(self.project)
		self.assertEqual(result["total"], 15000)
		self.assertEqual(result["original_scope_total"], 15000)
		self.assertEqual(result["change_orders_total"], 0)

	def test_total_always_equals_original_plus_change_orders(self):
		self._make_so(70000)
		co_so_1 = self._make_so(10000)
		co_so_2 = self._make_so(5000)
		self._make_co(co_so_1, co_number="CO-1", submit=True)
		self._make_co(co_so_2, co_number="CO-2", submit=True)

		result = change_orders.get_contract_value_breakdown(self.project)
		self.assertEqual(
			result["original_scope_total"] + result["change_orders_total"], result["total"]
		)
		self.assertEqual(result["total"], 85000)

	# -- gates ------------------------------------------------------------------------------

	def test_financial_gate_denies_viewer_and_allows_manager(self):
		frappe.set_user(self.viewer_user)
		with self.assertRaises(frappe.PermissionError):
			change_orders.get_contract_value_breakdown(self.project)

		frappe.set_user(self.manager_user)
		change_orders.get_contract_value_breakdown(self.project)  # must not raise


def _make_project(company):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-CO-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_sales_order(project, company, amount, submit=True):
	doc = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": _CUSTOMER,
			"company": company,
			"project": project,
			"delivery_date": today(),
			"items": [{"item_code": _ITEM_CODE, "qty": 1, "rate": amount}],
		}
	)
	doc.insert(ignore_permissions=True)
	if submit:
		doc.submit()
	return doc.name
