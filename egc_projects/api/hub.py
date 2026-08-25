"""Whitelisted read API behind the Project Hub (docs/ARCHITECTURE.md §5).

Every method here is a pure read. It resolves the governing `Project` (directly, or via a
child record's own `project` for `get_document_revisions`), gates on
`validators.require_project_permission` first, and returns plain dicts/lists built from
`frappe.get_all` — never `frappe.db.sql`. Nothing caller-supplied is interpolated into a query
string; filter dictionaries are checked against a per-endpoint allow-list of fieldnames before
they ever reach `frappe.get_all`.

This module owns no business state. Every derived value here (overdue, approval status, link
counts, ...) is recomputed from records owned by `document_control.py` / `submittal_control.py`
/ `relationships.py` / `egc_activity.py`; it is never re-derived with different logic.
"""

from __future__ import annotations

import erpnext
import frappe
from frappe import _
from frappe.utils import getdate, today

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import validators
from egc_projects.egc_projects.doctype.egc_activity.egc_activity import is_overdue as activity_is_overdue

#: How many rows each `recent` bucket in `get_overview` surfaces.
_RECENT_LIMIT = 10


# --- filter handling ---------------------------------------------------------------------


def _parse_filters(filters) -> dict:
	if not filters:
		return {}
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	if not isinstance(filters, dict):
		frappe.throw(_("Filters must be a JSON object."), exc=frappe.ValidationError)
	return filters


def _validated_filters(filters, allowed: set[str]) -> dict:
	"""Keep only allow-listed fieldnames; reject anything else outright.

	This bounds *which fields* a caller may filter on. `frappe.get_all` already parametrises
	every value, so this is a whitelist of query shape, not an injection guard on its own.
	"""
	parsed = _parse_filters(filters)
	unknown = set(parsed) - allowed
	if unknown:
		frappe.throw(
			_("Unknown filter field(s): {0}. Allowed: {1}").format(
				", ".join(sorted(unknown)), ", ".join(sorted(allowed))
			),
			title=_("Invalid Filter"),
			exc=frappe.ValidationError,
		)
	return {key: value for key, value in parsed.items() if value not in (None, "")}


# --- financial gate -----------------------------------------------------------------------


def _has_financial_access() -> bool:
	return bool(set(frappe.get_roles()) & set(c.FINANCIAL_ROLES))


def _require_financial_access() -> None:
	if not _has_financial_access():
		frappe.throw(
			_("You do not have permission to view project financials."),
			title=_("Not Permitted"),
			exc=frappe.PermissionError,
		)


# --- drawings helper (shared with the Drawing Register report) ----------------------------


def get_drawing_document_types() -> list[str]:
	"""Every `EGC Document Type` flagged `is_drawing = 1`. A drawing is this, nothing else."""
	return frappe.get_all("EGC Document Type", filters={"is_drawing": 1}, pluck="name")


# --- get_project_context --------------------------------------------------------------------


@frappe.whitelist()
def get_project_context(project: str) -> dict:
	validators.require_project_permission(project)

	row = frappe.db.get_value(
		"Project",
		project,
		[
			"project_name",
			"status",
			"customer",
			"expected_start_date",
			"expected_end_date",
			"percent_complete",
			"company",
		],
		as_dict=True,
	)
	currency = erpnext.get_company_currency(row.company) if row.company else None

	return {
		"project": project,
		"project_name": row.project_name,
		"status": row.status,
		"customer": row.customer,
		"dates": {
			"expected_start_date": row.expected_start_date,
			"expected_end_date": row.expected_end_date,
		},
		"percent_complete": row.percent_complete,
		"company": row.company,
		"currency": currency,
		"permissions": {"financials": _has_financial_access()},
	}


# --- get_overview ----------------------------------------------------------------------------


def _activity_overview(project: str) -> dict:
	by_status = {
		row.status: row.count
		for row in frappe.get_all(
			"EGC Activity",
			filters={"project": project},
			fields=["status", {"COUNT": "name", "as": "count"}],
			group_by="status",
		)
	}
	overdue_rows = frappe.get_all(
		"EGC Activity",
		filters=[
			["project", "=", project],
			# The "is set" guard is load-bearing. Frappe wraps a `<` filter on a nullable field
			# as `IFNULL(field, '') < value` (it skips this only for `>`/`>=` on dates — see
			# frappe/database/query.py `_should_apply_ifnull`), so an activity with no planned
			# finish would compare `'' < today()` and be counted as overdue. That contradicts
			# `egc_activity.is_overdue()`, which is the authority: no date means not overdue.
			["planned_end_date", "is", "set"],
			["planned_end_date", "<", today()],
			["status", "not in", list(c.ACTIVITY_CLOSED_STATUSES)],
		],
		fields=[{"COUNT": "name", "as": "count"}],
	)
	return {
		"total": sum(by_status.values()),
		"completed": by_status.get(c.ACTIVITY_COMPLETED, 0),
		"in_progress": by_status.get(c.ACTIVITY_IN_PROGRESS, 0),
		"not_started": by_status.get(c.ACTIVITY_NOT_STARTED, 0),
		"overdue": overdue_rows[0]["count"] if overdue_rows else 0,
	}


def _submittal_overview(project: str) -> dict:
	by_status = {
		row.submittal_status: row.count
		for row in frappe.get_all(
			"EGC Submittal",
			filters={"project": project},
			fields=["submittal_status", {"COUNT": "name", "as": "count"}],
			group_by="submittal_status",
		)
	}
	overdue_rows = frappe.get_all(
		"EGC Submittal",
		filters=[
			["project", "=", project],
			# Same IFNULL trap as `_activity_overview`: a submittal with no review due date is
			# not overdue, and `get_submittals`/the Submittal Log report both already say so.
			["current_due_date", "is", "set"],
			["current_due_date", "<", today()],
			["submittal_status", "in", list(c.SUBMISSION_OPEN_STATUSES)],
		],
		fields=[{"COUNT": "name", "as": "count"}],
	)
	return {
		"total": sum(by_status.values()),
		"approved": by_status.get(c.RESPONSE_APPROVED, 0),
		"approved_with_comments": by_status.get(c.RESPONSE_APPROVED_WITH_COMMENTS, 0),
		"under_review": sum(by_status.get(status, 0) for status in c.SUBMISSION_OPEN_STATUSES),
		"revise_resubmit": by_status.get(c.RESPONSE_REVISE_AND_RESUBMIT, 0),
		"rejected": by_status.get(c.RESPONSE_REJECTED, 0),
		"overdue": overdue_rows[0]["count"] if overdue_rows else 0,
	}


def _drawing_overview(project: str) -> dict:
	types = get_drawing_document_types()
	if not types:
		return {"total": 0, "issued": 0, "pending_review": 0}

	base_filters = {"project": project, "document_type": ("in", types)}
	by_document_status = frappe.get_all(
		"EGC Project Document",
		filters=base_filters,
		fields=["document_status", {"COUNT": "name", "as": "count"}],
		group_by="document_status",
	)
	by_approval_status = frappe.get_all(
		"EGC Project Document",
		filters=base_filters,
		fields=["approval_status", {"COUNT": "name", "as": "count"}],
		group_by="approval_status",
	)
	return {
		"total": sum(row["count"] for row in by_document_status),
		"issued": sum(row["count"] for row in by_document_status if row.document_status == c.DOCUMENT_ISSUED),
		"pending_review": sum(
			row["count"] for row in by_approval_status if row.approval_status == c.APPROVAL_UNDER_REVIEW
		),
	}


def _recent_activity(project: str) -> dict:
	document_revisions = frappe.get_all(
		"EGC Project Document Revision",
		filters={"project": project},
		fields=["name", "document", "revision", "revision_status", "revision_date", "modified"],
		order_by="modified desc",
		limit=_RECENT_LIMIT,
	)
	submittal_responses = frappe.get_all(
		"EGC Submittal Revision",
		filters={"project": project, "submission_status": c.SUBMISSION_RESPONDED},
		fields=["name", "submittal", "revision_label", "response", "response_date", "responded_by"],
		order_by="response_date desc, modified desc",
		limit=_RECENT_LIMIT,
	)
	activity_updates = frappe.get_all(
		"EGC Activity",
		filters={"project": project},
		fields=["name", "activity_code", "activity_name", "status", "percent_complete", "modified"],
		order_by="modified desc",
		limit=_RECENT_LIMIT,
	)
	return {
		"document_revisions": document_revisions,
		"submittal_responses": submittal_responses,
		"activity_updates": activity_updates,
	}


@frappe.whitelist()
def get_overview(project: str) -> dict:
	validators.require_project_permission(project)

	return {
		"activities": _activity_overview(project),
		"submittals": _submittal_overview(project),
		"drawings": _drawing_overview(project),
		"recent": _recent_activity(project),
	}


# --- get_wbs_tree ------------------------------------------------------------------------------


@frappe.whitelist()
def get_wbs_tree(project: str) -> list[dict]:
	validators.require_project_permission(project)

	return frappe.get_all(
		"EGC WBS Node",
		filters={"project": project},
		fields=[
			"name",
			"wbs_code",
			"wbs_name",
			"parent_egc_wbs_node as parent",
			"is_group",
			"sequence",
			"status",
			"discipline",
		],
		order_by="lft asc",
	)


# --- get_activities ------------------------------------------------------------------------------

_ACTIVITY_FILTER_FIELDS = {"status", "discipline", "wbs_node", "responsible_user", "is_group", "parent_egc_activity"}


def _activity_link_counts(activity_names: list[str]) -> dict[str, dict[str, int]]:
	if not activity_names:
		return {}
	rows = frappe.get_all(
		"EGC Activity Link",
		filters={"activity": ("in", activity_names)},
		fields=["activity", "link_doctype", {"COUNT": "name", "as": "count"}],
		group_by="activity, link_doctype",
	)
	counts: dict[str, dict[str, int]] = {}
	for row in rows:
		counts.setdefault(row.activity, {})[row.link_doctype] = row["count"]
	return counts


@frappe.whitelist()
def get_activities(project: str, filters=None) -> list[dict]:
	validators.require_project_permission(project)

	query_filters = _validated_filters(filters, _ACTIVITY_FILTER_FIELDS)
	query_filters["project"] = project

	rows = frappe.get_all(
		"EGC Activity",
		filters=query_filters,
		fields=[
			"name",
			"activity_code",
			"activity_name",
			"parent_egc_activity",
			"is_group",
			"sequence",
			"wbs_node",
			"discipline",
			"planned_start_date",
			"planned_end_date",
			"status",
			"percent_complete",
			"responsible_user",
		],
		order_by="lft asc",
	)
	if not rows:
		return []

	link_counts = _activity_link_counts([row.name for row in rows])
	for row in rows:
		row["is_overdue"] = activity_is_overdue(row.status, row.planned_end_date)
		row["link_counts"] = link_counts.get(row.name, {})
	return rows


# --- get_submittals ------------------------------------------------------------------------------

_SUBMITTAL_FILTER_FIELDS = {"submittal_type", "discipline", "wbs_node", "submittal_status"}


@frappe.whitelist()
def get_submittals(project: str, filters=None) -> list[dict]:
	validators.require_project_permission(project)

	query_filters = _validated_filters(filters, _SUBMITTAL_FILTER_FIELDS)
	query_filters["project"] = project

	rows = frappe.get_all(
		"EGC Submittal",
		filters=query_filters,
		fields=[
			"name",
			"submittal_number",
			"title",
			"submittal_type",
			"discipline",
			"wbs_node",
			"current_submission",
			"current_submission_label",
			"submittal_status",
			"current_due_date",
			"last_response_date",
		],
		order_by="submittal_number asc",
	)
	current_today = getdate(today())
	for row in rows:
		row["is_overdue"] = bool(
			row.current_due_date
			and getdate(row.current_due_date) < current_today
			and row.submittal_status in c.SUBMISSION_OPEN_STATUSES
		)
	return rows


# --- get_drawings --------------------------------------------------------------------------------

_DRAWING_FILTER_FIELDS = {"discipline", "approval_status", "document_type"}


@frappe.whitelist()
def get_drawings(project: str, filters=None) -> list[dict]:
	validators.require_project_permission(project)

	query_filters = _validated_filters(filters, _DRAWING_FILTER_FIELDS)

	drawing_types = get_drawing_document_types()
	if not drawing_types:
		return []

	requested_type = query_filters.pop("document_type", None)
	if requested_type:
		if requested_type not in drawing_types:
			# Not a drawing document type at all — the register never shows it, regardless.
			return []
		query_filters["document_type"] = requested_type
	else:
		query_filters["document_type"] = ("in", drawing_types)

	query_filters["project"] = project

	return frappe.get_all(
		"EGC Project Document",
		filters=query_filters,
		fields=[
			"name as document",
			"document_number as number",
			"title",
			"discipline",
			"current_revision_label",
			"approval_status",
			"current_revision_date",
			"current_file",
		],
		order_by="document_number asc",
	)


# --- get_document_revisions -----------------------------------------------------------------------


@frappe.whitelist()
def get_document_revisions(document: str) -> list[dict]:
	if not document or not frappe.db.exists("EGC Project Document", document):
		frappe.throw(_("Document {0} not found.").format(document), exc=frappe.DoesNotExistError)

	project = validators.get_project_of("EGC Project Document", document)
	validators.require_project_permission(project)

	return frappe.get_all(
		"EGC Project Document Revision",
		filters={"document": document},
		fields=[
			"revision",
			"revision_seq",
			"revision_status",
			"file",
			"revision_date",
			"issue_date",
			"remarks",
			"docstatus",
		],
		order_by="revision_seq desc",
	)


# --- get_financials --------------------------------------------------------------------------------

_FINANCIAL_PROJECT_FIELDS = (
	"total_billed_amount",
	"total_purchase_cost",
	"total_consumed_material_cost",
	"total_costing_amount",
	"total_billable_amount",
	"total_sales_amount",
	"estimated_costing",
	"gross_margin",
	"per_gross_margin",
	"company",
)


@frappe.whitelist()
def get_financials(project: str) -> dict:
	validators.require_project_permission(project)
	_require_financial_access()

	# Read straight off `tabProject` — ERPNext/HRMS controllers already maintain these figures.
	# Re-aggregating Sales/Purchase Invoices, Timesheets, Stock Entries or Expense Claims here
	# would create a second, divergent source of truth. See docs/ARCHITECTURE.md §6.
	row = frappe.db.get_value("Project", project, _FINANCIAL_PROJECT_FIELDS, as_dict=True)

	expense_claims = None
	if frappe.get_meta("Project").has_field("total_expense_claim"):
		expense_claims = frappe.db.get_value("Project", project, "total_expense_claim")

	currency = erpnext.get_company_currency(row.company) if row.company else None

	return {
		"billed": row.total_billed_amount,
		"purchase_cost": row.total_purchase_cost,
		"expense_claims": expense_claims,
		"consumed_material_cost": row.total_consumed_material_cost,
		"timesheet_cost": row.total_costing_amount,
		"billable": row.total_billable_amount,
		"sales_order_value": row.total_sales_amount,
		"estimated_costing": row.estimated_costing,
		"gross_margin": row.gross_margin,
		"per_gross_margin": row.per_gross_margin,
		"currency": currency,
	}
