"""Whitelisted API behind the Hub's Financials tab contract-value breakdown.

Option C (Round 3 design discussion): `EGC Change Order` owns the approval process; the linked
Sales Order owns the actual number. This module reconciles the two into the display the user
asked for verbatim — "the total contract value is X, the original scope was Y and then an amount
in Z was CHANGE orders" — by partitioning the SAME set of submitted Sales Orders core's own
`Project.update_sales_amount()` already sums into `total_sales_amount`:

- Total (X)          = every submitted Sales Order of the project (core's own figure, unchanged).
- Change Orders (Z)   = the subset wrapped by a submitted (docstatus 1 — "approved") Change Order.
- Original Scope (Y)  = everything else.

Y + Z always equals X by construction, since every submitted Sales Order falls into exactly one
side of that partition — there is no separate running total to drift out of sync.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import validators


def _require_financial_access() -> None:
	# Mirrors api/hub.py's own gate of the same name exactly (same c.FINANCIAL_ROLES) — a
	# contract-value breakdown is financial data by the same standard the Financials tab already
	# applies, so it is gated identically rather than importing a private helper cross-module.
	if not set(frappe.get_roles()) & set(c.FINANCIAL_ROLES):
		frappe.throw(
			_("You do not have permission to view project financials."),
			title=_("Not Permitted"),
			exc=frappe.PermissionError,
		)


@frappe.whitelist()
def get_contract_value_breakdown(project: str) -> dict:
	validators.require_project_permission(project)
	_require_financial_access()

	sales_orders = frappe.get_all(
		"Sales Order",
		filters={"project": project, "docstatus": 1},
		fields=["name", "base_net_total"],
	)
	total = sum(flt(row.base_net_total) for row in sales_orders)

	change_orders = frappe.get_all(
		"EGC Change Order",
		filters={"project": project, "docstatus": 1},
		fields=["name", "co_number", "title", "sales_order", "amount", "approval_date", "approved_by"],
		order_by="approval_date asc, creation asc",
	)
	change_orders_total = sum(flt(row.amount) for row in change_orders)
	original_scope_total = total - change_orders_total

	return {
		"total": total,
		"original_scope_total": original_scope_total,
		"change_orders_total": change_orders_total,
		"change_orders": change_orders,
		"sales_order_count": len(sales_orders),
	}


@frappe.whitelist()
def get_change_orders(project: str, status: str | None = None) -> list[dict]:
	"""Every Change Order of `project`, regardless of docstatus, for a management list view —
	`get_contract_value_breakdown` above only ever counts the submitted (approved) ones."""
	validators.require_project_permission(project)
	_require_financial_access()

	filters = {"project": project}
	if status == "Draft":
		filters["docstatus"] = 0
	elif status == "Approved":
		filters["docstatus"] = 1
	elif status == "Cancelled":
		filters["docstatus"] = 2

	return frappe.get_all(
		"EGC Change Order",
		filters=filters,
		fields=[
			"name",
			"co_number",
			"title",
			"sales_order",
			"amount",
			"docstatus",
			"reason",
			"requested_by",
			"approval_date",
			"approved_by",
			"creation",
		],
		order_by="creation desc",
	)
