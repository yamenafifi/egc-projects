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
from frappe.query_builder.functions import Coalesce, NullIf, Sum
from frappe.utils import add_days, flt, getdate, today

from egc_projects.egc_projects import action_items, constants as c
from egc_projects.egc_projects import project_profile, validators
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


# --- project info edit gate ------------------------------------------------------------------
#
# Project Information is edited on the native `Project` form now (ARCHITECTURE_V2.md §1), not
# through a Hub-side API — so "can edit" is exactly "can this user write to this Project",
# nothing bespoke layered on top. Kept as a named helper only because `get_project_context`
# surfaces it as a UI hint (show/hide the "Edit on Project" link).


def _has_profile_edit_access(project: str) -> bool:
	return bool(frappe.has_permission("Project", "write", doc=project))


# --- drawings helper (shared with the Drawing Register report) ----------------------------


def get_drawing_document_types() -> list[str]:
	"""Every `EGC Document Type` flagged `is_drawing = 1`. A drawing is this, nothing else."""
	return frappe.get_all("EGC Document Type", filters={"is_drawing": 1}, pluck="name")


# --- get_project_context --------------------------------------------------------------------


def _user_full_names(names: set[str]) -> dict[str, str]:
	if not names:
		return {}
	rows = frappe.get_all("User", filters={"name": ("in", list(names))}, fields=["name", "full_name"])
	return {row.name: row.full_name for row in rows}


def _project_profile_summary(project: str) -> dict:
	"""The header-relevant slice of Project Information (ARCHITECTURE_V2.md §1/§4).

	Always a dict, never None — the fields live directly on `Project` now, so there is no
	separate row whose absence would need representing. The full field set and full
	stakeholder/equipment lists are fetched separately via `get_project_info()`.
	"""
	raw = frappe.db.get_value(
		"Project",
		project,
		[
			"custom_egc_project_code",
			"custom_egc_project_stage",
			"custom_egc_sector",
			"custom_egc_project_image",
			"custom_egc_contract_value",
		],
		as_dict=True,
	)
	row = {
		"project_code": raw.custom_egc_project_code,
		"project_stage": raw.custom_egc_project_stage,
		"sector": raw.custom_egc_sector,
		"project_image": raw.custom_egc_project_image,
		"contract_value": raw.custom_egc_contract_value,
	}

	stakeholders = project_profile.get_stakeholders(project)
	key_roles = set(project_profile.KEY_STAKEHOLDER_ROLES)
	key_rows = [s for s in stakeholders if s.role in key_roles]
	full_names = _user_full_names({s.user for s in key_rows if s.user})

	row["key_stakeholders"] = [
		{
			"role": s.role,
			"role_label": s.role,
			"party_name": s.party_name,
			"organization": s.organization,
			"user": s.user,
			"user_full_name": full_names.get(s.user) if s.user else None,
		}
		for s in key_rows
	]
	return row


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
		"permissions": {"financials": _has_financial_access(), "edit_profile": _has_profile_edit_access(project)},
		"profile": _project_profile_summary(project),
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


# --- Project health (docs/ARCHITECTURE_V2.md §11) ----------------------------------------------
#
# Deliberately only these four, deliberately only this simple — "Only derive health where the
# rules are defensible" is the brief's own instruction. Each returns "green"/"orange"/"red".


def _schedule_health(project: str) -> str:
	overdue_rows = frappe.get_all(
		"EGC Activity",
		filters=[
			["project", "=", project],
			["planned_end_date", "is", "set"],
			["planned_end_date", "<", today()],
			["status", "not in", list(c.ACTIVITY_CLOSED_STATUSES)],
		],
		fields=["modified"],
	)
	if not overdue_rows:
		return "green"
	# "touched" = the Activity row itself was last modified within the window — a status change
	# is a save, so this is a safe proxy without a dedicated status-change-history field.
	cutoff = add_days(today(), -14)
	touched_recently = any(getdate(row.modified) >= getdate(cutoff) for row in overdue_rows)
	return "orange" if touched_recently else "red"


def _submittals_health(project: str) -> str:
	overdue = frappe.get_all(
		"EGC Submittal",
		filters=[
			["project", "=", project],
			["current_due_date", "is", "set"],
			["current_due_date", "<", today()],
			["submittal_status", "in", list(c.SUBMISSION_OPEN_STATUSES)],
		],
		limit=1,
	)
	if overdue:
		return "red"
	# `submittal_status` already IS the current submission's response (see `_refresh_from_current`
	# in submittal_control.py), so a Submittal sitting at Revise & Resubmit/Rejected has, by
	# definition, not yet been resubmitted — a new cycle would move it off that status.
	needs_resubmit = frappe.get_all(
		"EGC Submittal",
		filters={
			"project": project,
			"submittal_status": ("in", (c.RESPONSE_REVISE_AND_RESUBMIT, c.RESPONSE_REJECTED)),
		},
		limit=1,
	)
	return "orange" if needs_resubmit else "green"


def _governing_submission_due_date(current_revision: str) -> str | None:
	"""The due date of the SAME submission `document_control.get_approval_status` used to derive
	this revision's `approval_status` — mirrors that function's own query exactly (latest
	non-cancelled submitted submission carrying this revision) rather than picking a different
	submission and risking a health signal that disagrees with the status it is about."""
	rows = frappe.get_all(
		"EGC Submittal Revision",
		filters=[
			["EGC Submittal Revision", "docstatus", "=", 1],
			["EGC Submittal Revision", "submission_status", "!=", c.SUBMISSION_CANCELLED],
			["EGC Submittal Document Item", "document_revision", "=", current_revision],
		],
		fields=["due_date", "submission_seq"],
		order_by="submission_seq desc",
		limit=1,
	)
	return rows[0].due_date if rows else None


def _drawings_health(project: str) -> str:
	types = get_drawing_document_types()
	if not types:
		return "green"

	at_risk = frappe.get_all(
		"EGC Project Document",
		filters=[
			["project", "=", project],
			["document_type", "in", types],
			["approval_status", "in", (c.APPROVAL_UNDER_REVIEW, c.RESPONSE_REVISE_AND_RESUBMIT)],
			["current_revision", "is", "set"],
		],
		fields=["current_revision"],
	)
	today_date = getdate(today())
	for row in at_risk:
		due_date = _governing_submission_due_date(row.current_revision)
		if due_date and getdate(due_date) < today_date:
			return "orange"
	return "green"


def _financials_health(project: str) -> str:
	# Deliberately the simplest possible rule — a fabricated "budget variance" indicator with no
	# budget data behind it would violate the brief's own instruction not to fake a metric.
	gross_margin = frappe.db.get_value("Project", project, "gross_margin")
	return "red" if gross_margin is not None and flt(gross_margin) < 0 else "green"


def _project_health(project: str) -> dict:
	return {
		"schedule": _schedule_health(project),
		"submittals": _submittals_health(project),
		"documents": _drawings_health(project),
		"financials": _financials_health(project),
	}


@frappe.whitelist()
def get_overview(project: str) -> dict:
	validators.require_project_permission(project)

	return {
		"activities": _activity_overview(project),
		"submittals": _submittal_overview(project),
		"drawings": _drawing_overview(project),
		"recent": _recent_activity(project),
		"health": _project_health(project),
	}


# --- get_my_open_items (docs/ARCHITECTURE_V2.md §8) --------------------------------------------


@frappe.whitelist()
def get_my_open_items(project: str | None = None) -> list[dict]:
	if project:
		validators.require_project_permission(project)
	return action_items.get_open_items_for_user(frappe.session.user, project)


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
			"weight_pct",
			"responsible_user",
			"responsible_supplier",
			"duration_days",
			"is_milestone",
			"actual_start_date",
			"actual_end_date",
			"forecast_start_date",
			"forecast_end_date",
		],
		order_by="lft asc",
	)
	if not rows:
		return []

	link_counts = _activity_link_counts([row.name for row in rows])
	wbs_labels = _wbs_labels({row.wbs_node for row in rows if row.wbs_node})

	# Depth from the parent chain, exactly like the EGC Activity Status Summary report — `lft`
	# order guarantees a row's parent was already assigned its depth by the time this row is
	# visited, so one pass is enough; no need to re-walk the tree per row.
	depth_by_name: dict[str, int] = {}
	for row in rows:
		parent = row.parent_egc_activity
		row["indent"] = depth_by_name.get(parent, -1) + 1 if parent in depth_by_name else 0
		depth_by_name[row.name] = row["indent"]
		row["is_overdue"] = activity_is_overdue(row.status, row.planned_end_date)
		row["link_counts"] = link_counts.get(row.name, {})
		# The raw WBS record name is `{project}-{code}`, which reads as noise in a register
		# that is already scoped to one project. Send the code and name so the client can show
		# "01.02.01 HVAC" and still deep-link by `wbs_node`.
		row["wbs_label"] = wbs_labels.get(row.wbs_node)
	return rows


def _wbs_labels(names: set[str]) -> dict[str, str]:
	if not names:
		return {}
	rows = frappe.get_all(
		"EGC WBS Node", filters={"name": ("in", list(names))}, fields=["name", "wbs_code", "wbs_name"]
	)
	return {row.name: f"{row.wbs_code} {row.wbs_name}".strip() for row in rows}


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
			"ball_in_court",
			"responsible_party",
			"submittal_manager",
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

_DRAWING_FILTER_FIELDS = {"discipline", "approval_status", "document_type", "drawing_set", "drawing_area"}


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
			"drawing_set",
			"drawing_area",
			"drawing_date",
			"received_date",
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


# --- get_financial_transactions (docs/ARCHITECTURE_V2.md §10) -------------------------------
#
# Each helper reconstructs, transaction-by-transaction, EXACTLY the same query ERPNext/HRMS uses
# to arrive at the corresponding `get_financials()` figure (see `erpnext.projects.doctype.
# project.project.Project.update_costing`/`update_purchase_costing`/`update_billed_amount`, and
# `hrms.overrides.employee_project.EmployeeProject.update_costing` — this site's Project class is
# overridden to `EmployeeProject`, which is why `timesheet_cost` sums `costing_amount`, not
# `base_costing_amount`, and why `expense_claims` folds in the HRMS-only `total_expense_claim`).
# Never recompute the total independently here — a query that summed differently from the one
# that produced the headline figure would let the drill-down disagree with it, which is exactly
# what this endpoint exists to make impossible.


def _billed_transactions(project: str) -> list[dict]:
	si = frappe.qb.DocType("Sales Invoice")
	sii = frappe.qb.DocType("Sales Invoice Item")
	rows = (
		frappe.qb.from_(sii)
		.join(si)
		.on(si.name == sii.parent)
		.select(si.name, si.posting_date, si.customer, Sum(sii.base_net_amount).as_("amount"))
		.where(
			(si.docstatus == 1)
			& ((sii.project == project) | (sii.project.isnull() & (si.project == project)))
		)
		.groupby(si.name, si.posting_date, si.customer)
		.orderby(si.posting_date, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	for row in rows:
		row["doctype"] = "Sales Invoice"
		row["date"] = row.pop("posting_date")
		row["reference"] = row.pop("customer")
	return rows


def _purchase_cost_transactions(project: str) -> list[dict]:
	pi = frappe.qb.DocType("Purchase Invoice")
	pii = frappe.qb.DocType("Purchase Invoice Item")
	rows = (
		frappe.qb.from_(pii)
		.join(pi)
		.on(pi.name == pii.parent)
		.select(pi.name, pi.posting_date, pi.supplier, Sum(pii.base_net_amount).as_("amount"))
		.where((pi.docstatus == 1) & (pii.project == project))
		.groupby(pi.name, pi.posting_date, pi.supplier)
		.orderby(pi.posting_date, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	for row in rows:
		row["doctype"] = "Purchase Invoice"
		row["date"] = row.pop("posting_date")
		row["reference"] = row.pop("supplier")
	return rows


def _expense_claim_transactions(project: str) -> list[dict]:
	ec = frappe.qb.DocType("Expense Claim")
	ecd = frappe.qb.DocType("Expense Claim Detail")
	rows = (
		frappe.qb.from_(ecd)
		.join(ec)
		.on(ec.name == ecd.parent)
		.select(ec.name, ec.posting_date, ec.employee_name, Sum(ecd.sanctioned_amount).as_("amount"))
		.where(
			(ec.docstatus == 1)
			& (Coalesce(NullIf(ecd.project, ""), ec.project) == project)
		)
		.groupby(ec.name, ec.posting_date, ec.employee_name)
		.orderby(ec.posting_date, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	for row in rows:
		row["doctype"] = "Expense Claim"
		row["date"] = row.pop("posting_date")
		row["reference"] = row.pop("employee_name")
	return rows


def _consumed_material_transactions(project: str) -> list[dict]:
	se = frappe.qb.DocType("Stock Entry")
	sed = frappe.qb.DocType("Stock Entry Detail")
	rows = (
		frappe.qb.from_(sed)
		.join(se)
		.on(se.name == sed.parent)
		.select(se.name, se.posting_date, se.purpose, Sum(sed.amount).as_("amount"))
		.where(
			(sed.docstatus == 1)
			& (sed.project == project)
			& (sed.t_warehouse.isnull() | (sed.t_warehouse == ""))
		)
		.groupby(se.name, se.posting_date, se.purpose)
		.orderby(se.posting_date, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	# `update_costing`'s `total_consumed_material_cost` also folds in Landed Cost Taxes and
	# Charges rows on Manufacture-purpose Stock Entries — added onto the matching entry here so
	# a project with such entries still reconciles to the headline figure exactly.
	lc = frappe.qb.DocType("Landed Cost Taxes and Charges")
	landed = (
		frappe.qb.from_(se)
		.join(lc)
		.on(lc.parent == se.name)
		.select(se.name, Sum(lc.base_amount).as_("landed_amount"))
		.where((se.docstatus == 1) & (se.project == project) & (se.purpose == "Manufacture"))
		.groupby(se.name)
		.run(as_dict=True)
	)
	landed_by_name = {row.name: row.landed_amount for row in landed}
	for row in rows:
		row["amount"] = flt(row["amount"]) + flt(landed_by_name.get(row.name, 0))
		row["doctype"] = "Stock Entry"
		row["date"] = row.pop("posting_date")
		row["reference"] = row.pop("purpose")
	return rows


def _timesheet_transactions(project: str) -> list[dict]:
	ts = frappe.qb.DocType("Timesheet")
	tsd = frappe.qb.DocType("Timesheet Detail")
	rows = (
		frappe.qb.from_(tsd)
		.join(ts)
		.on(ts.name == tsd.parent)
		.select(ts.name, ts.start_date, ts.employee_name, Sum(tsd.costing_amount).as_("amount"))
		.where((tsd.docstatus == 1) & (tsd.project == project))
		.groupby(ts.name, ts.start_date, ts.employee_name)
		.orderby(ts.start_date, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	for row in rows:
		row["doctype"] = "Timesheet"
		row["date"] = row.pop("start_date")
		row["reference"] = row.pop("employee_name")
	return rows


def _sales_order_transactions(project: str) -> list[dict]:
	rows = frappe.get_all(
		"Sales Order",
		filters={"project": project, "docstatus": 1},
		fields=["name", "transaction_date as date", "customer as reference", "base_net_total as amount"],
		order_by="transaction_date desc",
	)
	for row in rows:
		row["doctype"] = "Sales Order"
	return rows


_FINANCIAL_TRANSACTION_FNS = {
	"billed": _billed_transactions,
	"purchase_cost": _purchase_cost_transactions,
	"expense_claims": _expense_claim_transactions,
	"consumed_material_cost": _consumed_material_transactions,
	"timesheet_cost": _timesheet_transactions,
	"sales_order_value": _sales_order_transactions,
}


@frappe.whitelist()
def get_financial_transactions(project: str, metric: str) -> list[dict]:
	validators.require_project_permission(project)
	_require_financial_access()

	fn = _FINANCIAL_TRANSACTION_FNS.get(metric)
	if not fn:
		frappe.throw(
			_("{0} is not a drill-down-able financial metric.").format(frappe.bold(metric)),
			exc=frappe.ValidationError,
		)
	return fn(project)


# --- Project Information: get_project_info, read-only (ARCHITECTURE_V2.md §1) -----------------
#
# There is no `save_project_info` — this data is edited on the native `Project` form, the same
# way egc_hr's Supervisors/Project Location fields already are. This endpoint exists only to
# give the Hub's own read-side (a curated summary view, not a duplicate edit form) a single call
# instead of one `frappe.db.get_value` per field.

#: External name -> the actual `custom_egc_*` fieldname on `Project`. Keeps the Hub-facing
#: contract stable and free of Frappe's custom-field naming convention, and is the one place
#: that would need editing if a field were ever renamed on `Project` itself.
_PROFILE_FIELD_MAP = {
	"project_code": "custom_egc_project_code",
	"project_stage": "custom_egc_project_stage",
	"sector": "custom_egc_sector",
	"delivery_method": "custom_egc_delivery_method",
	"contract_type": "custom_egc_contract_type",
	"project_description": "custom_egc_project_description",
	"work_scope": "custom_egc_work_scope",
	"contract_value": "custom_egc_contract_value",
	"project_image": "custom_egc_project_image",
	"country": "custom_egc_country",
	"region": "custom_egc_region",
	"city": "custom_egc_city",
	"address": "custom_egc_address",
	"time_zone": "custom_egc_time_zone",
	"site_contact_name": "custom_egc_site_contact_name",
	"site_contact_phone": "custom_egc_site_contact_phone",
	"site_contact_email": "custom_egc_site_contact_email",
	"contract_date": "custom_egc_contract_date",
	"forecast_completion_date": "custom_egc_forecast_completion_date",
	"warranty_start_date": "custom_egc_warranty_start_date",
	"dlp_end_date": "custom_egc_dlp_end_date",
}

_STAKEHOLDER_ROW_FIELDS = ("role", "party_name", "organization", "user", "contact", "email", "phone", "is_primary")
_EQUIPMENT_ROW_FIELDS = (
	"facility",
	"department",
	"modality",
	"wbs_node",
	"equipment_manufacturer",
	"equipment_model",
	"oem_reference",
	"equipment_delivery_target",
	"room_ready_target",
	"oem_installation_target",
	"commissioning_target",
	"notes",
)


@frappe.whitelist()
def get_project_info(project: str) -> dict:
	validators.require_project_permission(project)

	raw = frappe.db.get_value("Project", project, list(_PROFILE_FIELD_MAP.values()), as_dict=True)
	data = {external: raw[internal] for external, internal in _PROFILE_FIELD_MAP.items()}
	data["project"] = project
	data["stakeholders"] = project_profile.get_stakeholders(project)
	data["equipment_items"] = frappe.get_all(
		"EGC Project Equipment Item",
		filters={"parent": project, "parenttype": "Project"},
		fields=list(_EQUIPMENT_ROW_FIELDS),
		order_by="idx asc",
	)
	return data
