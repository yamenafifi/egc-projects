# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""EGC Change Order — the approval process around a contract-value increase.

Option C from the Round 3 design discussion: this doctype owns the APPROVAL PROCESS; the linked
Sales Order owns the actual NUMBER. Submitting a Change Order (docstatus 1) IS the approval step
— there is no separate Status field to keep in sync with docstatus, matching this app's existing
submittable-doctype convention (EGC Submittal Revision, EGC Project Document Revision).

`api/change_orders.py`'s `get_contract_value_breakdown` is what actually reconciles Total =
Original Scope + Change Orders: Original Scope is every submitted Sales Order of the project NOT
wrapped by a submitted Change Order; Change Orders is every submitted Sales Order that IS. Both
sides read `Sales Order.base_net_total` directly — the exact figure core's own
`Project.update_sales_amount()` sums into `total_sales_amount` — so the two halves always add up
to the project's existing headline contract value with no second source of truth.

FROZEN (Level 1 §37) — see `api/change_orders.py`'s own module docstring. This doctype is a
deliberately simple approval wrapper, not the app's real commercial architecture; it isn't the
foundation to build cost/schedule impact, Change Events, or the client-vs-vendor distinction on
top of. That design belongs to Level 5 (§60).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from egc_projects.egc_projects import validators


class EGCChangeOrder(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		amount: DF.Currency
		approval_date: DF.Date | None
		approved_by: DF.Link | None
		co_number: DF.Data
		project: DF.Link
		reason: DF.Text | None
		remarks: DF.SmallText | None
		requested_by: DF.Link | None
		sales_order: DF.Link
		title: DF.Data
	# end: auto-generated types

	def validate(self):
		self._validate_co_number_unique()
		validators.validate_same_project(self, "sales_order", "Sales Order", _("Sales Order"))
		self._validate_sales_order_submitted()
		self._validate_sales_order_not_already_wrapped()
		self._sync_amount()

	def _validate_co_number_unique(self):
		# Deliberately NOT `validators.validate_unique_in_project` here: this doctype's `autoname`
		# is `format:{project}-{co_number}`, so a genuine duplicate computes the SAME `self.name`
		# as the existing row before `validate()` even runs. That shared helper's "exclude
		# `name != self.name`" guard would then exclude the very row being duplicated, letting a
		# collision fall through to a raw DB `DuplicateEntryError` instead of this friendly
		# message. Using `self.is_new()` instead of a name comparison sidesteps that: a brand new
		# doc never needs to exclude anything, so any match at all is a genuine duplicate.
		value = (self.co_number or "").strip()
		if not value or not self.project:
			return
		self.co_number = value

		filters = {"project": self.project, "co_number": value}
		if not self.is_new():
			filters["name"] = ("!=", self.name)
		existing = frappe.db.get_value("EGC Change Order", filters, "name")
		if existing:
			frappe.throw(
				_("CO Number {0} already exists in project {1} ({2}).").format(
					frappe.bold(value), frappe.bold(self.project), existing
				),
				title=_("Duplicate CO Number"),
				exc=frappe.ValidationError,
			)

	def _validate_sales_order_not_already_wrapped(self):
		# Deliberately NOT a DB-level unique constraint: that would also block the standard
		# cancel-then-amend flow, since a cancelled Change Order (docstatus 2) still occupies its
		# old `sales_order` value in the table. Excluding docstatus 2 (and self) here allows an
		# amended replacement to reuse the same Sales Order while still preventing two live
		# Change Orders from double-counting one Sales Order's amount.
		existing = frappe.db.get_value(
			"EGC Change Order",
			{
				"sales_order": self.sales_order,
				"docstatus": ("!=", 2),
				"name": ("!=", self.name or ""),
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("Sales Order {0} is already wrapped by Change Order {1}.").format(
					frappe.bold(self.sales_order), frappe.bold(existing)
				),
				title=_("Already Wrapped"),
				exc=frappe.ValidationError,
			)

	def _validate_sales_order_submitted(self):
		docstatus = frappe.db.get_value("Sales Order", self.sales_order, "docstatus")
		if docstatus != 1:
			frappe.throw(
				_(
					"Sales Order {0} must be submitted before it can be wrapped in a Change Order."
				).format(frappe.bold(self.sales_order)),
				title=_("Sales Order Not Submitted"),
				exc=frappe.ValidationError,
			)

	def _sync_amount(self):
		# Never entered directly — always re-read from the Sales Order, the single source of
		# truth for the number itself (see this module's docstring, Option C).
		self.amount = frappe.db.get_value("Sales Order", self.sales_order, "base_net_total") or 0

	def on_submit(self):
		self.approval_date = today()
		self.approved_by = frappe.session.user
