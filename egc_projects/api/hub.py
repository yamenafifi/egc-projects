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
from frappe.contacts.doctype.address.address import render_address
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
			"custom_egc_project_stage",
			"custom_egc_sector",
			"custom_egc_project_image",
			"custom_egc_project_description",
		],
		as_dict=True,
	)
	row = {
		"project_stage": raw.custom_egc_project_stage,
		"sector": raw.custom_egc_sector,
		"project_image": raw.custom_egc_project_image,
		"project_description": raw.custom_egc_project_description,
	}

	stakeholders = project_profile.get_stakeholders(project)
	key_roles = set(project_profile.KEY_STAKEHOLDER_ROLES)
	key_rows = [s for s in stakeholders if s.role in key_roles]

	row["key_stakeholders"] = [
		{
			"role": s.role,
			"role_label": s.role,
			"party_name": s.party_name,
			"organization": s.organization,
			# `person` links directly to a User now — no separate identity record to resolve.
			"person": s.person,
		}
		for s in key_rows
	]
	return row


@frappe.whitelist()
def get_my_projects() -> list[dict]:
	"""Every project the CALLING user can currently see — the Hub's own landing page
	(`ProjectPicker.vue`, at the bare `/app/project-manager` route) reads this to show a
	browsable list instead of a bare search box.

	Deliberately `frappe.get_list` (permission-respecting), never `frappe.get_all` — this is the
	whole payoff of fixing `grant_portal_access`'s admin-bypass bug (api/directory.py): a bypass
	role holder (System Manager/Projects Manager) now carries zero restrictive `Project` User
	Permission rows, so `get_list` naturally returns every project for them; everyone else
	naturally gets only their scoped project(s). No bypass logic needed here at all."""
	return frappe.get_list(
		"Project", fields=["name", "project_name", "status"], order_by="modified desc"
	)


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


def _activity_rows(project: str) -> list[dict]:
	"""Every Activity's status/planned_end_date/modified for this project — the one query shared
	by `_activity_overview` (status tally + overdue count) and `_schedule_health` (overdue rows'
	own `modified` dates), which used to each run their own separate, near-identical query even
	though `get_overview()` always calls both in the same request."""
	return frappe.get_all(
		"EGC Activity",
		filters={"project": project},
		fields=["status", "planned_end_date", "modified"],
	)


def _is_activity_overdue(row, today_date) -> bool:
	# Same rule as `egc_activity.is_overdue()`, evaluated in Python against an already-fetched
	# row instead of a fresh DB filter — no date means not overdue, full stop.
	return bool(
		row.planned_end_date
		and getdate(row.planned_end_date) < today_date
		and row.status not in c.ACTIVITY_CLOSED_STATUSES
	)


def _activity_overview(rows: list[dict]) -> dict:
	today_date = getdate(today())
	by_status: dict[str, int] = {}
	overdue = 0
	for row in rows:
		by_status[row.status] = by_status.get(row.status, 0) + 1
		if _is_activity_overdue(row, today_date):
			overdue += 1
	return {
		"total": len(rows),
		"completed": by_status.get(c.ACTIVITY_COMPLETED, 0),
		"in_progress": by_status.get(c.ACTIVITY_IN_PROGRESS, 0),
		"not_started": by_status.get(c.ACTIVITY_NOT_STARTED, 0),
		"overdue": overdue,
	}


def _submittal_rows(project: str) -> list[dict]:
	"""Every Submittal's submittal_status/current_due_date for this project — the one query
	shared by `_submittal_overview` and `_submittals_health`, same reasoning as `_activity_rows`."""
	return frappe.get_all(
		"EGC Submittal",
		filters={"project": project},
		fields=["submittal_status", "current_due_date"],
	)


def _is_submittal_overdue(row, today_date) -> bool:
	return bool(
		row.current_due_date
		and getdate(row.current_due_date) < today_date
		and row.submittal_status in c.SUBMISSION_OPEN_STATUSES
	)


def _submittal_overview(rows: list[dict]) -> dict:
	today_date = getdate(today())
	by_status: dict[str, int] = {}
	overdue = 0
	for row in rows:
		by_status[row.submittal_status] = by_status.get(row.submittal_status, 0) + 1
		if _is_submittal_overdue(row, today_date):
			overdue += 1
	return {
		"total": len(rows),
		"approved": by_status.get(c.RESPONSE_APPROVED, 0),
		"approved_with_comments": by_status.get(c.RESPONSE_APPROVED_WITH_COMMENTS, 0),
		"under_review": sum(by_status.get(status, 0) for status in c.SUBMISSION_OPEN_STATUSES),
		"revise_resubmit": by_status.get(c.RESPONSE_REVISE_AND_RESUBMIT, 0),
		"rejected": by_status.get(c.RESPONSE_REJECTED, 0),
		"overdue": overdue,
	}


def _drawing_overview(project: str, types: list[str]) -> dict:
	if not types:
		return {"total": 0, "issued": 0, "pending_review": 0, "approved": 0}

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
		"approved": sum(
			row["count"] for row in by_approval_status if row.approval_status == c.RESPONSE_APPROVED
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


def _schedule_health(rows: list[dict]) -> str:
	today_date = getdate(today())
	overdue_rows = [row for row in rows if _is_activity_overdue(row, today_date)]
	if not overdue_rows:
		return "green"
	# "touched" = the Activity row itself was last modified within the window — a status change
	# is a save, so this is a safe proxy without a dedicated status-change-history field.
	cutoff = add_days(today(), -14)
	touched_recently = any(getdate(row.modified) >= getdate(cutoff) for row in overdue_rows)
	return "orange" if touched_recently else "red"


def _submittals_health(rows: list[dict]) -> str:
	today_date = getdate(today())
	if any(_is_submittal_overdue(row, today_date) for row in rows):
		return "red"
	# `submittal_status` already IS the current submission's response (see `_refresh_from_current`
	# in submittal_control.py), so a Submittal sitting at Revise & Resubmit/Rejected has, by
	# definition, not yet been resubmitted — a new cycle would move it off that status.
	needs_resubmit = any(
		row.submittal_status in (c.RESPONSE_REVISE_AND_RESUBMIT, c.RESPONSE_REJECTED) for row in rows
	)
	return "orange" if needs_resubmit else "green"


def _governing_submission_due_dates(current_revisions: list[str]) -> dict[str, str | None]:
	"""The due date of the SAME submission `document_control.get_approval_status` used to derive
	each revision's `approval_status` — mirrors that function's own query exactly (latest
	non-cancelled submitted submission carrying this revision) rather than picking a different
	submission and risking a health signal that disagrees with the status it is about.

	Batched across every at-risk revision in one query (`document_revision IN (...)`, then the
	highest `submission_seq` per revision kept in Python) — `_drawings_health` used to call the
	single-revision version of this once per at-risk drawing, an N+1 on the Hub's own landing tab.
	"""
	if not current_revisions:
		return {}
	rows = frappe.get_all(
		"EGC Submittal Revision",
		filters=[
			["EGC Submittal Revision", "docstatus", "=", 1],
			["EGC Submittal Revision", "submission_status", "!=", c.SUBMISSION_CANCELLED],
			["EGC Submittal Document Item", "document_revision", "in", current_revisions],
		],
		fields=[
			"due_date",
			"submission_seq",
			"`tabEGC Submittal Document Item`.document_revision as document_revision",
		],
		order_by="submission_seq desc",
	)
	result: dict[str, str | None] = {}
	for row in rows:
		# First occurrence per revision wins — rows are already ordered by submission_seq desc,
		# so that's the highest-numbered (most recent) submission for that revision.
		result.setdefault(row.document_revision, row.due_date)
	return result


def _drawings_health(project: str, types: list[str]) -> str:
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
	if not at_risk:
		return "green"

	due_dates = _governing_submission_due_dates([row.current_revision for row in at_risk])
	today_date = getdate(today())
	for row in at_risk:
		due_date = due_dates.get(row.current_revision)
		if due_date and getdate(due_date) < today_date:
			return "orange"
	return "green"


def _financials_health(project: str) -> str | None:
	# Deliberately the simplest possible rule — a fabricated "budget variance" indicator with no
	# budget data behind it would violate the brief's own instruction not to fake a metric.
	# `None` (the key is dropped entirely by `_project_health`) when the caller has no financial
	# access — a red/green signal derived from `gross_margin` is itself a commercial figure, and
	# `get_financials()` already refuses the same user outright via `_require_financial_access()`;
	# this used to leak that exact figure's sign to anyone who could merely open the Overview tab.
	if not _has_financial_access():
		return None
	gross_margin = frappe.db.get_value("Project", project, "gross_margin")
	return "red" if gross_margin is not None and flt(gross_margin) < 0 else "green"


def _project_health(project: str, activity_rows: list[dict], submittal_rows: list[dict], drawing_types: list[str]) -> dict:
	health = {
		"schedule": _schedule_health(activity_rows),
		"submittals": _submittals_health(submittal_rows),
		"documents": _drawings_health(project, drawing_types),
	}
	financials = _financials_health(project)
	if financials is not None:
		health["financials"] = financials
	return health


@frappe.whitelist()
def get_overview(project: str) -> dict:
	validators.require_project_permission(project)

	activity_rows = _activity_rows(project)
	submittal_rows = _submittal_rows(project)
	drawing_types = get_drawing_document_types()

	return {
		"activities": _activity_overview(activity_rows),
		"submittals": _submittal_overview(submittal_rows),
		"drawings": _drawing_overview(project, drawing_types),
		"recent": _recent_activity(project),
		"health": _project_health(project, activity_rows, submittal_rows, drawing_types),
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

_ACTIVITY_FILTER_FIELDS = {"status", "discipline", "wbs_node", "is_group", "parent_egc_activity"}


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


def _activity_assignees(activity_names: list[str]) -> dict[str, list[dict]]:
	"""Batched replacement for the old single `responsible_user`/`responsible_supplier` columns
	— every EGC Assignment row for these Activities in one query, grouped back by Activity, for
	a compact "people chips" display in the register without a round-trip per row."""
	if not activity_names:
		return {}
	rows = frappe.get_all(
		"EGC Assignment",
		filters={"parent_doctype": "EGC Activity", "parent_name": ("in", activity_names)},
		fields=["parent_name", "assignment_role", "is_primary", "person_label", "organization_type", "organization"],
		order_by="is_primary desc, creation asc",
	)
	if not rows:
		return {}
	customer_names = {row.organization for row in rows if row.organization and row.organization_type == "Customer"}
	supplier_names = {row.organization for row in rows if row.organization and row.organization_type == "Supplier"}
	org_labels = {
		o.name: o.customer_name
		for o in (
			frappe.get_all("Customer", filters={"name": ("in", list(customer_names))}, fields=["name", "customer_name"])
			if customer_names
			else []
		)
	}
	org_labels.update(
		{
			o.name: o.supplier_name
			for o in (
				frappe.get_all("Supplier", filters={"name": ("in", list(supplier_names))}, fields=["name", "supplier_name"])
				if supplier_names
				else []
			)
		}
	)
	grouped: dict[str, list[dict]] = {}
	for row in rows:
		grouped.setdefault(row.parent_name, []).append(
			{
				"label": row.person_label or org_labels.get(row.organization) or row.organization,
				"assignment_role": row.assignment_role,
				"is_primary": row.is_primary,
			}
		)
	return grouped


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
	assignees = _activity_assignees([row.name for row in rows])
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
		row["assignees"] = assignees.get(row.name, [])
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


def _expense_claims_or_none(project: str) -> float | None:
	"""`Project.total_expense_claim` only exists when HRMS is installed — `None` (not `0`) when
	it isn't, so `get_financials()` can show "—" rather than a misleading "$0.00" for a site that
	never tracked expense claims at all. Shared by `get_financials()`/`get_cost_forecast()`,
	which used to each run this exact `has_field` + `get_value` pair independently."""
	if not frappe.get_meta("Project").has_field("total_expense_claim"):
		return None
	return frappe.db.get_value("Project", project, "total_expense_claim")


@frappe.whitelist()
def get_financials(project: str) -> dict:
	validators.require_project_permission(project)
	_require_financial_access()

	# Read straight off `tabProject` — ERPNext/HRMS controllers already maintain these figures.
	# Re-aggregating Sales/Purchase Invoices, Timesheets, Stock Entries or Expense Claims here
	# would create a second, divergent source of truth. See docs/ARCHITECTURE.md §6.
	row = frappe.db.get_value("Project", project, _FINANCIAL_PROJECT_FIELDS, as_dict=True)

	expense_claims = _expense_claims_or_none(project)

	currency = erpnext.get_company_currency(row.company) if row.company else None

	return {
		"billed": row.total_billed_amount,
		"purchase_cost": row.total_purchase_cost,
		"committed_purchase_orders": _committed_purchase_orders_total(project),
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


# --- get_cost_forecast ------------------------------------------------------------------------
#
# Earned Value Management, using the Activity-weighted `Project.percent_complete` (see
# project_progress.py) as the "physical % complete" — the number weight_pct exists to make
# trustworthy. Standard formulas (budget = BAC, spent-to-date = AC):
#
#   Earned Value (EV)  = Budget x % Complete           — the budgeted worth of work actually done
#   Cost Performance Index (CPI) = EV / Actual Cost     — spending efficiency so far (1.0 = on plan)
#   Estimate at Completion (EAC) = Budget / CPI         — forecast TOTAL cost, given that efficiency
#   Estimate to Complete (ETC)   = EAC - Actual Cost     — "how much money I still need to spend"
#
# With no Actual Cost yet, CPI is undefined and EAC falls back to the plain Budget (no evidence
# yet to deviate from it) — so ETC is simply the full Budget, exactly as expected before any
# money has been spent.
#
# EXPERIMENTAL (Level 1 §36): this is textbook EVM shaped around one number this app doesn't
# actually have yet — a per-Activity BUDGETED cost. `percent_complete` is a physical-progress
# proxy (weight_pct's own weighting, not a dollar weighting), so "Earned Value" here is really
# "budget x physical progress", not a certified cost-loaded EVM figure. Correct once real
# cost-loaded budgeting exists; until then, this function's only caller (FinancialsTab.vue) must
# keep it visibly marked as a rough estimate, never presented as a contractual forecast.

_COST_FORECAST_PROJECT_FIELDS = (
	"estimated_costing",
	"total_purchase_cost",
	"total_consumed_material_cost",
	"total_costing_amount",
	"percent_complete",
	"company",
)


@frappe.whitelist()
def get_cost_forecast(project: str) -> dict:
	validators.require_project_permission(project)
	_require_financial_access()

	row = frappe.db.get_value("Project", project, _COST_FORECAST_PROJECT_FIELDS, as_dict=True)

	expense_claims = flt(_expense_claims_or_none(project))

	budget = flt(row.estimated_costing)
	actual_cost = (
		flt(row.total_purchase_cost)
		+ flt(row.total_consumed_material_cost)
		+ flt(row.total_costing_amount)
		+ expense_claims
	)
	percent_complete = flt(row.percent_complete)

	earned_value = budget * percent_complete / 100
	cpi = earned_value / actual_cost if actual_cost > 0 else None
	estimate_at_completion = budget / cpi if cpi else budget
	estimate_to_complete = estimate_at_completion - actual_cost

	currency = erpnext.get_company_currency(row.company) if row.company else None

	return {
		"budget": budget,
		"percent_complete": percent_complete,
		"actual_cost": actual_cost,
		"earned_value": earned_value,
		"cost_performance_index": cpi,
		"estimate_at_completion": estimate_at_completion,
		"estimate_to_complete": max(estimate_to_complete, 0),
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


# A submitted Purchase Order is a commitment to spend, not a cost yet — ERPNext only ever counts
# it towards `Project.total_purchase_cost` once it has actually been invoiced (see
# `calculate_total_purchase_cost()`, which sums Purchase Invoice Item, never Purchase Order Item
# at all). That's correct accrual accounting, but it also means a project can carry real,
# submitted Purchase Orders that are completely invisible on the Financials tab until someone
# raises an invoice against them — which reads as "my Purchase Orders are being ignored". This
# shows that money separately as its own figure instead of folding it into `purchase_cost` (which
# must stay true "already invoiced" for `get_cost_forecast()`'s CPI/EAC math to mean anything).
# `per_billed` nets out the portion already invoiced so a partially-billed PO isn't double-counted
# against `purchase_cost`; `status != "Closed"` excludes POs someone has deliberately short-closed
# (no further invoice is coming, so the unbilled remainder is no longer a real commitment).
def _committed_purchase_order_transactions(project: str) -> list[dict]:
	po = frappe.qb.DocType("Purchase Order")
	rows = (
		frappe.qb.from_(po)
		.select(po.name, po.transaction_date, po.supplier, po.base_net_total, po.per_billed)
		.where((po.docstatus == 1) & (po.project == project) & (po.status != "Closed"))
		.orderby(po.transaction_date, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	for row in rows:
		base_net_total = flt(row.pop("base_net_total"))
		per_billed = flt(row.pop("per_billed"))
		row["amount"] = max(base_net_total * (100 - per_billed) / 100, 0)
		row["doctype"] = "Purchase Order"
		row["date"] = row.pop("transaction_date")
		row["reference"] = row.pop("supplier")
	return [row for row in rows if row["amount"] > 0]


def _committed_purchase_orders_total(project: str) -> float:
	return sum(flt(row["amount"]) for row in _committed_purchase_order_transactions(project))


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


# --- Cash Flow (Payment Entry — real cash movement, not invoiced-but-maybe-unpaid) --------------
#
# Never queried anywhere in this app before this: ERPNext's Payment Entry already carries a
# native `project` field, just never surfaced. Two real limitations disclosed in the UI, not
# hidden: `project` is only auto-set when a payment is created from a Sales/Purchase Order or
# Invoice (not from Bank Reconciliation, Payment Reconciliation, or a bare New Payment Entry), so
# a project's real cash flow can be under-reported by any payment entered through those other
# paths. And one Payment Entry can only ever belong to one project (`Payment Entry Reference` has
# no `project` field of its own) — a payment reconciling invoices from multiple projects can't be
# split proportionally; that's a structural ERPNext limitation, not something a query can fix.
# `base_received_amount`/`base_paid_amount` (company currency) are used throughout, never the
# bare `paid_amount`/`received_amount` — those are denominated in the paid-from/paid-to account's
# own currency, not company currency, so summing them raw across multi-currency payments would be
# meaningless. `unallocated_amount` (an advance beyond what the source document actually needed)
# is surfaced as its own disclosed figure, never netted invisibly into received/paid — neither
# choice is obviously "more correct", so this doesn't pretend to have resolved that ambiguity.


def _cash_flow_transactions(project: str) -> list[dict]:
	pe = frappe.qb.DocType("Payment Entry")
	rows = (
		frappe.qb.from_(pe)
		.select(
			pe.name,
			pe.posting_date,
			pe.payment_type,
			pe.party,
			pe.reference_no,
			pe.base_received_amount,
			pe.base_paid_amount,
		)
		.where((pe.docstatus == 1) & (pe.project == project) & (pe.payment_type.isin(["Receive", "Pay"])))
		.orderby(pe.posting_date, order=frappe.qb.desc)
		.run(as_dict=True)
	)
	for row in rows:
		party = row.pop("party")
		reference_no = row.pop("reference_no")
		received = flt(row.pop("base_received_amount"))
		paid = flt(row.pop("base_paid_amount"))
		row["doctype"] = "Payment Entry"
		row["date"] = row.pop("posting_date")
		row["reference"] = party or reference_no or None
		row["amount"] = received if row["payment_type"] == "Receive" else -paid
	return rows


@frappe.whitelist()
def get_cash_flow(project: str) -> dict:
	validators.require_project_permission(project)
	_require_financial_access()

	pe = frappe.qb.DocType("Payment Entry")
	rows = (
		frappe.qb.from_(pe)
		.select(
			pe.payment_type,
			Sum(pe.base_received_amount).as_("received"),
			Sum(pe.base_paid_amount).as_("paid"),
			Sum(pe.unallocated_amount).as_("unallocated"),
		)
		.where((pe.docstatus == 1) & (pe.project == project) & (pe.payment_type.isin(["Receive", "Pay"])))
		.groupby(pe.payment_type)
		.run(as_dict=True)
	)
	received = 0.0
	paid = 0.0
	unallocated = 0.0
	for row in rows:
		if row.payment_type == "Receive":
			received = flt(row.received)
		else:
			paid = flt(row.paid)
		unallocated += flt(row.unallocated)

	company = frappe.db.get_value("Project", project, "company")
	currency = erpnext.get_company_currency(company) if company else None

	return {
		"received": received,
		"paid": paid,
		"net": received - paid,
		"unallocated": unallocated,
		"currency": currency,
	}


_FINANCIAL_TRANSACTION_FNS = {
	"billed": _billed_transactions,
	"purchase_cost": _purchase_cost_transactions,
	"committed_purchase_orders": _committed_purchase_order_transactions,
	"expense_claims": _expense_claim_transactions,
	"consumed_material_cost": _consumed_material_transactions,
	"timesheet_cost": _timesheet_transactions,
	"sales_order_value": _sales_order_transactions,
	"cash_flow": _cash_flow_transactions,
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


# --- get_portfolio_overview (the bare `/app/project-manager` landing dashboard) ----------------
#
# Everything below reuses the SAME formulas as get_financials()/_committed_purchase_order_
# transactions() above, evaluated once across every project the caller can see instead of once
# per project. Six of the seven metrics are linear sums and collapse cleanly into one grouped
# query each; committed Purchase Orders is the one exception — its per-row amount is
# `base_net_total * (100-per_billed)/100`, a product of two columns, so it can't collapse into a
# SQL SUM without duplicating that formula in a second place. That one instead broadens its WHERE
# to every visible project and sums in Python, reusing the exact same per-row formula — still one
# round trip, zero formula duplication.
#
# The project list itself is never accepted from the caller — always `_portfolio_projects()`'s
# own permission-respecting `frappe.get_list` result, the same primitive `get_my_projects()`
# already relies on. That's what keeps "check permission once, trust every row after" (this
# file's existing project-isolation model) safe when applied in bulk instead of per-project.


def _portfolio_projects() -> list[str]:
	return frappe.get_list("Project", pluck="name")


def _billed_by_project(projects: list[str]) -> dict[str, float]:
	si = frappe.qb.DocType("Sales Invoice")
	sii = frappe.qb.DocType("Sales Invoice Item")
	project_expr = Coalesce(sii.project, si.project)
	rows = (
		frappe.qb.from_(sii)
		.join(si)
		.on(si.name == sii.parent)
		.select(project_expr.as_("project"), Sum(sii.base_net_amount).as_("amount"))
		.where((si.docstatus == 1) & project_expr.isin(projects))
		.groupby(project_expr)
		.run(as_dict=True)
	)
	return {row.project: flt(row.amount) for row in rows}


def _purchase_cost_by_project(projects: list[str]) -> dict[str, float]:
	pi = frappe.qb.DocType("Purchase Invoice")
	pii = frappe.qb.DocType("Purchase Invoice Item")
	rows = (
		frappe.qb.from_(pii)
		.join(pi)
		.on(pi.name == pii.parent)
		.select(pii.project.as_("project"), Sum(pii.base_net_amount).as_("amount"))
		.where((pi.docstatus == 1) & pii.project.isin(projects))
		.groupby(pii.project)
		.run(as_dict=True)
	)
	return {row.project: flt(row.amount) for row in rows}


def _committed_purchase_orders_by_project(projects: list[str]) -> dict[str, float]:
	po = frappe.qb.DocType("Purchase Order")
	rows = (
		frappe.qb.from_(po)
		.select(po.project, po.base_net_total, po.per_billed)
		.where((po.docstatus == 1) & po.project.isin(projects) & (po.status != "Closed"))
		.run(as_dict=True)
	)
	totals: dict[str, float] = {}
	for row in rows:
		amount = max(flt(row.base_net_total) * (100 - flt(row.per_billed)) / 100, 0)
		totals[row.project] = totals.get(row.project, 0) + amount
	return totals


def _expense_claims_by_project(projects: list[str]) -> dict[str, float]:
	if not frappe.get_meta("Project").has_field("total_expense_claim"):
		return {}
	ec = frappe.qb.DocType("Expense Claim")
	ecd = frappe.qb.DocType("Expense Claim Detail")
	project_expr = Coalesce(NullIf(ecd.project, ""), ec.project)
	rows = (
		frappe.qb.from_(ecd)
		.join(ec)
		.on(ec.name == ecd.parent)
		.select(project_expr.as_("project"), Sum(ecd.sanctioned_amount).as_("amount"))
		.where((ec.docstatus == 1) & project_expr.isin(projects))
		.groupby(project_expr)
		.run(as_dict=True)
	)
	return {row.project: flt(row.amount) for row in rows}


def _consumed_material_by_project(projects: list[str]) -> dict[str, float]:
	se = frappe.qb.DocType("Stock Entry")
	sed = frappe.qb.DocType("Stock Entry Detail")
	rows = (
		frappe.qb.from_(sed)
		.join(se)
		.on(se.name == sed.parent)
		.select(sed.project.as_("project"), Sum(sed.amount).as_("amount"))
		.where((sed.docstatus == 1) & sed.project.isin(projects) & (sed.t_warehouse.isnull() | (sed.t_warehouse == "")))
		.groupby(sed.project)
		.run(as_dict=True)
	)
	totals = {row.project: flt(row.amount) for row in rows}

	lc = frappe.qb.DocType("Landed Cost Taxes and Charges")
	landed_rows = (
		frappe.qb.from_(se)
		.join(lc)
		.on(lc.parent == se.name)
		.select(se.project.as_("project"), Sum(lc.base_amount).as_("amount"))
		.where((se.docstatus == 1) & se.project.isin(projects) & (se.purpose == "Manufacture"))
		.groupby(se.project)
		.run(as_dict=True)
	)
	for row in landed_rows:
		totals[row.project] = totals.get(row.project, 0) + flt(row.amount)
	return totals


def _timesheet_cost_by_project(projects: list[str]) -> dict[str, float]:
	ts = frappe.qb.DocType("Timesheet")
	tsd = frappe.qb.DocType("Timesheet Detail")
	rows = (
		frappe.qb.from_(tsd)
		.join(ts)
		.on(ts.name == tsd.parent)
		.select(tsd.project.as_("project"), Sum(tsd.costing_amount).as_("amount"))
		.where((tsd.docstatus == 1) & tsd.project.isin(projects))
		.groupby(tsd.project)
		.run(as_dict=True)
	)
	return {row.project: flt(row.amount) for row in rows}


def _sales_order_value_by_project(projects: list[str]) -> dict[str, float]:
	rows = frappe.get_all(
		"Sales Order",
		filters={"project": ("in", projects), "docstatus": 1},
		fields=["project", {"SUM": "base_net_total", "as": "amount"}],
		group_by="project",
	)
	return {row.project: flt(row.amount) for row in rows}


@frappe.whitelist()
def get_portfolio_overview() -> dict:
	"""The bare `/app/project-manager` landing dashboard's one data source — every project the
	caller can see, its financial totals, and a health rollup, gated identically to every other
	financial endpoint in this file (`_require_financial_access()`). Never called for a user
	without that role: `EgcProjectHub.vue` falls back to the plain `ProjectPicker` instead, same
	as it already does today for a bare URL with nothing to auto-open."""
	_require_financial_access()

	projects = _portfolio_projects()
	if not projects:
		return {"projects": [], "needs_attention": []}

	project_rows = frappe.get_all(
		"Project",
		filters={"name": ("in", projects)},
		fields=["name", "project_name", "status", "company", "gross_margin", "percent_complete"],
		order_by="modified desc",
	)

	billed = _billed_by_project(projects)
	purchase_cost = _purchase_cost_by_project(projects)
	committed_purchase_orders = _committed_purchase_orders_by_project(projects)
	expense_claims = _expense_claims_by_project(projects)
	consumed_material_cost = _consumed_material_by_project(projects)
	timesheet_cost = _timesheet_cost_by_project(projects)
	sales_order_value = _sales_order_value_by_project(projects)

	# Global, not per-project — the same list `get_overview()` already fetches once per call;
	# fetched once here too rather than once per project in the loop below.
	drawing_types = get_drawing_document_types()

	result_projects = []
	needs_attention = []
	for row in project_rows:
		currency = erpnext.get_company_currency(row.company) if row.company else None
		financials = {
			"billed": billed.get(row.name, 0),
			"purchase_cost": purchase_cost.get(row.name, 0),
			"committed_purchase_orders": committed_purchase_orders.get(row.name, 0),
			"expense_claims": expense_claims.get(row.name),
			"consumed_material_cost": consumed_material_cost.get(row.name, 0),
			"timesheet_cost": timesheet_cost.get(row.name, 0),
			"sales_order_value": sales_order_value.get(row.name, 0),
			"gross_margin": row.gross_margin,
			"currency": currency,
		}

		# Same signals `get_overview()` already computes per-project — reused, not re-derived
		# with different logic, so a project flagged here shows the identical health on its own
		# Overview tab, never a portfolio-only signal a user can't cross-check.
		activity_rows = _activity_rows(row.name)
		submittal_rows = _submittal_rows(row.name)
		health = _project_health(row.name, activity_rows, submittal_rows, drawing_types)

		entry = {
			"project": row.name,
			"project_name": row.project_name,
			"status": row.status,
			"percent_complete": row.percent_complete,
			"financials": financials,
			"health": health,
		}
		result_projects.append(entry)

		if "red" in (health.get("financials"), health.get("schedule"), health.get("submittals")):
			needs_attention.append({"project": row.name, "project_name": row.project_name, "health": health})

	return {"projects": result_projects, "needs_attention": needs_attention}


# --- Project Information: get_project_info (Level 0 §8) ----------------------------------------
#
# Read-side only — `save_project_profile`/`add_stakeholder`/`remove_stakeholder`/
# `add_equipment_item`/`remove_equipment_item` (the write side) live in `project_profile.py`
# alongside the field maps they share with this function, not here.


@frappe.whitelist()
def get_project_info(project: str) -> dict:
	validators.require_project_permission(project)

	raw = frappe.db.get_value("Project", project, list(project_profile.PROFILE_FIELD_MAP.values()), as_dict=True)
	data = {external: raw[internal] for external, internal in project_profile.PROFILE_FIELD_MAP.items()}
	data["project"] = project
	# `project_address` is only ever the Address doctype's own record name (an autoname hash) —
	# format it into a real display string here so the Hub never has to reimplement address
	# formatting, matching the "one address model, shared with the rest of ERPNext" point of
	# switching to a real Address record in the first place.
	# `render_address(..., check_permissions=False)`, not `get_address_display` — access here is
	# already gated by `require_project_permission` above; a Hub user who can read this Project
	# shouldn't ALSO need one of core Address's own business-specific roles (Sales User,
	# Purchase User, ...) just to see its own linked address, the same way none of this
	# function's other fetched display fields re-check permission on their source doctype.
	data["project_address_display"] = (
		render_address(data["project_address"], check_permissions=False) if data.get("project_address") else None
	)
	data["stakeholders"] = project_profile.get_stakeholders(project)
	data["equipment_items"] = frappe.get_all(
		"EGC Project Equipment Item",
		filters={"parent": project, "parenttype": "Project"},
		fields=["name", *project_profile.EQUIPMENT_ROW_FIELDS],
		order_by="idx asc",
	)
	return data
