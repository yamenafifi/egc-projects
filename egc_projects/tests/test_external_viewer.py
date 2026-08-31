# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""EGC External Viewer (constants.ROLE_EXTERNAL_VIEWER) — for an external party (Main
Contractor, Client, Consultant, ...) given their own login, always paired with a User
Permission scoping them to the one Project they're allowed to see. Same read-only doctype
footprint as EGC Project Viewer, but never financial: proves the role can read ordinary
project data yet is denied Financials/Change Orders, exactly like the Hub's own financial
gate, and that a User Permission genuinely fences it to one project.
"""

import frappe
from frappe.permissions import add_user_permission
from frappe.tests import IntegrationTestCase

from egc_projects.api import change_orders, hub
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


def _make_project(company):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-ExtViewer-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


class TestExternalViewer(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]

	def setUp(self):
		frappe.set_user("Administrator")
		self.project = _make_project(self.company)
		self.other_project = _make_project(self.company)
		self.external_user = _get_or_create_user(
			f"egc-mc-{frappe.generate_hash(length=6)}@example.com",
			["Projects User", c.ROLE_EXTERNAL_VIEWER],
		)
		add_user_permission("Project", self.project, self.external_user, ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_can_read_ordinary_project_data(self):
		frappe.set_user(self.external_user)
		# Must not raise — the whole point of the role is real read access to non-financial
		# Hub data for the one project it's scoped to.
		hub.get_activities(self.project)
		hub.get_drawings(self.project)
		hub.get_overview(self.project)

	def test_cannot_see_financials(self):
		frappe.set_user(self.external_user)
		with self.assertRaises(frappe.PermissionError):
			hub.get_financials(self.project)

	def test_cannot_see_change_order_breakdown(self):
		frappe.set_user(self.external_user)
		with self.assertRaises(frappe.PermissionError):
			change_orders.get_contract_value_breakdown(self.project)

	def test_change_order_doctype_denies_direct_read(self):
		# The doctype-level permission gate, independent of the Hub API gate above — an
		# external (or even internal Project Viewer) user must never see EGC Change Order
		# through the native list/report view either.
		frappe.set_user(self.external_user)
		self.assertFalse(frappe.has_permission("EGC Change Order", "read"))

	def test_cannot_see_a_project_not_granted(self):
		frappe.set_user(self.external_user)
		with self.assertRaises(frappe.PermissionError):
			hub.get_activities(self.other_project)

	def test_internal_project_viewer_also_denied_change_order(self):
		# Regression: EGC Change Order's doctype permissions used to list EGC Project Viewer
		# (and EGC Project Engineer) as read-only, contradicting the Hub API's own
		# FINANCIAL_ROLES gate — fixed alongside adding the External Viewer role.
		viewer = _get_or_create_user(
			f"egc-piv-{frappe.generate_hash(length=6)}@example.com",
			["Projects User", c.ROLE_PROJECT_VIEWER],
		)
		frappe.set_user(viewer)
		self.assertFalse(frappe.has_permission("EGC Change Order", "read"))

	def test_financial_fields_not_reachable_via_raw_field_read(self):
		"""Regression for a real bypass: `hub.get_financials()`'s own `_require_financial_access()`
		gate only protects that one whitelisted method — it does nothing to the underlying
		`Project` fields themselves. Before `install.py.restrict_financial_field_permlevel()`,
		every role with plain `read` on `Project` (which is every role a Hub account needs,
		including `Projects User`) could read these same figures via a raw
		`frappe.client.get_value`/REST call, completely bypassing the Hub's own gate.
		`frappe.model.get_permitted_fields` is the exact function that field-filtering REST/report
		access goes through, so it is a faithful proxy for "can this user read this field at all,
		by any path" — not just whether one whitelisted method happens to check first."""
		from frappe.model import get_permitted_fields

		frappe.set_user(self.external_user)
		fields = get_permitted_fields("Project", user=self.external_user, permission_type="read")
		self.assertNotIn("total_billed_amount", fields)
		self.assertNotIn("gross_margin", fields)
		self.assertNotIn("total_purchase_cost", fields)

	def test_financial_fields_reachable_by_a_financial_role(self):
		manager = _get_or_create_user(
			f"egc-pm-{frappe.generate_hash(length=6)}@example.com",
			["Projects User", c.ROLE_PROJECT_MANAGER],
		)
		from frappe.model import get_permitted_fields

		fields = get_permitted_fields("Project", user=manager, permission_type="read")
		self.assertIn("total_billed_amount", fields)
		self.assertIn("gross_margin", fields)

	def test_financial_fields_writable_by_a_financial_role(self):
		# Regression: `restrict_financial_field_permlevel()` granted `read` at permlevel 3 but
		# never `write` — a real bug a user actually hit ("estimated cost is greyed out, I can't
		# change it"), since there is no Hub-native way to edit these fields either
		# (`api/hub.py` only ever reads them). `get_permitted_fields` only proves read reachability
		# (used above); write access needs `frappe.model.get_permitted_fields(..., "write")` — or,
		# more directly, checking the field itself isn't `read_only` per `frappe.permissions`.
		manager = _get_or_create_user(
			f"egc-pm-write-{frappe.generate_hash(length=6)}@example.com",
			["Projects User", c.ROLE_PROJECT_MANAGER],
		)
		from frappe.model import get_permitted_fields

		fields = get_permitted_fields("Project", user=manager, permission_type="write")
		self.assertIn("estimated_costing", fields)
		self.assertIn("total_billed_amount", fields)

	def test_financial_fields_not_writable_without_a_financial_role(self):
		viewer = _get_or_create_user(
			f"egc-piv-write-{frappe.generate_hash(length=6)}@example.com",
			["Projects User", c.ROLE_PROJECT_VIEWER],
		)
		from frappe.model import get_permitted_fields

		fields = get_permitted_fields("Project", user=viewer, permission_type="write")
		self.assertNotIn("estimated_costing", fields)
