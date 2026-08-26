"""Whitelisted API behind the Hub's Submittals tab and the Submittal detail workspace
(docs/ARCHITECTURE_V2.md §7, §9-§16 of the original brief, §12 of the addendum).

Follows `api/documents.py`'s conventions verbatim: `validators.require_project_permission`
first, `frappe.get_all` only, no raw SQL. The multi-step workflow transitions themselves
(`apply_workflow_template`, `add_review_step`, `record_step_response`, `mark_under_review`,
`record_response`, `create_next_revision`) already live as whitelisted functions in
`submittal_control.py` — this module does not re-wrap them, it only adds what that module
doesn't own: submittal creation, rich detail assembly, and workflow-template listing/creation.
"""

from __future__ import annotations

import frappe
from frappe import _

from egc_projects.egc_projects import relationships, submittal_control, validators

# --- create_submittal ("+ New Submittal" from the Hub) ----------------------------------------

_CREATE_FIELDS = ("submittal_number", "title", "submittal_type", "discipline", "wbs_node", "description",
	"responsible_party", "received_from", "submittal_manager", "specification_section")


@frappe.whitelist()
def create_submittal(project: str, **kwargs) -> dict:
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC Submittal", "create", throw=True)

	values = {field: kwargs.get(field) for field in _CREATE_FIELDS if kwargs.get(field) is not None}
	for required in ("submittal_number", "title", "submittal_type"):
		if not values.get(required):
			frappe.throw(_("{0} is required.").format(required), exc=frappe.ValidationError)

	doc = frappe.get_doc({"doctype": "EGC Submittal", "project": project, **values})
	doc.insert()
	return {"name": doc.name}


# --- get_submittal_detail --------------------------------------------------------------------

_SUBMITTAL_FIELDS = (
	"name",
	"project",
	"submittal_number",
	"title",
	"submittal_type",
	"discipline",
	"wbs_node",
	"description",
	"responsible_party",
	"received_from",
	"submittal_manager",
	"specification_section",
	"current_submission",
	"current_submission_label",
	"current_due_date",
	"last_response_date",
	"submittal_status",
	"ball_in_court",
)

_SUBMISSION_FIELDS = (
	"name",
	"revision_label",
	"submission_seq",
	"date_submitted",
	"due_date",
	"required_submission_date",
	"required_approval_date",
	"final_due_date",
	"required_on_site_date",
	"lead_time_days",
	"submitted_by",
	"reviewer",
	"submission_status",
	"response",
	"response_date",
	"responded_by",
	"response_remarks",
	"ball_in_court_label",
	"docstatus",
)

_STEP_FIELDS = (
	"name",
	"sequence",
	"reviewer_role",
	"reviewer_user",
	"reviewer_label",
	"is_required",
	"status",
	"response",
	"response_date",
	"responded_by",
	"response_remarks",
)


def _submission_documents(submission: str) -> list[dict]:
	return frappe.get_all(
		"EGC Submittal Document Item",
		filters={"parent": submission},
		fields=["document_revision", "document", "revision", "document_title"],
		order_by="idx asc",
	)


@frappe.whitelist()
def get_submittal_detail(submittal: str) -> dict:
	if not submittal or not frappe.db.exists("EGC Submittal", submittal):
		frappe.throw(_("Submittal {0} not found.").format(submittal), exc=frappe.DoesNotExistError)

	project = validators.get_project_of("EGC Submittal", submittal)
	validators.require_project_permission(project)

	submittal_doc = frappe.db.get_value("EGC Submittal", submittal, _SUBMITTAL_FIELDS, as_dict=True)

	submissions = frappe.get_all(
		"EGC Submittal Revision",
		filters={"submittal": submittal},
		fields=list(_SUBMISSION_FIELDS),
		order_by="submission_seq desc",
	)
	submission_names = [row.name for row in submissions]

	steps_by_submission: dict[str, list[dict]] = {name: [] for name in submission_names}
	if submission_names:
		steps = frappe.get_all(
			"EGC Submittal Review Step",
			filters={"submittal_revision": ("in", submission_names)},
			fields=[*_STEP_FIELDS, "submittal_revision"],
			order_by="sequence asc, creation asc",
		)
		for step in steps:
			steps_by_submission[step.submittal_revision].append(step)

	for row in submissions:
		row["documents"] = _submission_documents(row.name)
		row["steps"] = steps_by_submission.get(row.name, [])

	return {
		"submittal": submittal_doc,
		"submissions": submissions,
		# Reverse direction of EGC Activity Link — every Activity linked to this Submittal.
		"related_activities": relationships.get_activities_for("EGC Submittal", submittal),
	}


# --- workflow templates ------------------------------------------------------------------------


@frappe.whitelist()
def get_workflow_templates() -> list[dict]:
	return frappe.get_all(
		"EGC Submittal Workflow Template",
		fields=["name", "template_name", "description"],
		order_by="template_name asc",
	)


@frappe.whitelist()
def get_workflow_template_detail(template: str) -> dict:
	doc = frappe.get_doc("EGC Submittal Workflow Template", template)
	return {
		"name": doc.name,
		"template_name": doc.template_name,
		"description": doc.description,
		"steps": [
			{
				"sequence": row.sequence,
				"reviewer_role": row.reviewer_role,
				"is_required": row.is_required,
				"label": row.label,
			}
			for row in doc.steps
		],
	}


@frappe.whitelist()
def create_workflow_template(template_name: str, steps, description: str | None = None) -> str:
	"""`steps` arrives as a JSON-encoded string over a real HTTP call — see
	docs/ARCHITECTURE_V2.md's note on `api/wbs.py`'s `reorder_wbs_nodes`/`bulk_create_wbs_nodes`
	for why this parameter is deliberately untyped rather than annotated `list[dict]`."""
	frappe.has_permission("EGC Submittal Workflow Template", "create", throw=True)

	if isinstance(steps, str):
		steps = frappe.parse_json(steps)

	doc = frappe.get_doc(
		{
			"doctype": "EGC Submittal Workflow Template",
			"template_name": template_name,
			"description": description,
			"steps": [
				{
					"sequence": row.get("sequence"),
					"reviewer_role": row.get("reviewer_role"),
					"is_required": row.get("is_required", 1),
					"label": row.get("label"),
				}
				for row in (steps or [])
			],
		}
	)
	doc.insert()
	return doc.name


# --- My Open Items support: submittals awaiting the current user's response -------------------


@frappe.whitelist()
def get_my_open_reviews(project: str | None = None) -> list[dict]:
	filters = {"reviewer_user": frappe.session.user, "status": "In Review"}
	steps = frappe.get_all(
		"EGC Submittal Review Step",
		filters=filters,
		fields=["name", "submittal_revision", "project"],
	)
	if project:
		steps = [s for s in steps if s.project == project]
	if not steps:
		return []

	revision_names = [s.submittal_revision for s in steps]
	revisions = frappe.get_all(
		"EGC Submittal Revision",
		filters={"name": ("in", revision_names)},
		fields=["name", "submittal", "revision_label", "due_date"],
	)
	revision_by_name = {r.name: r for r in revisions}

	submittal_names = list({r.submittal for r in revisions})
	submittals = frappe.get_all(
		"EGC Submittal",
		filters={"name": ("in", submittal_names)},
		fields=["name", "submittal_number", "title", "project"],
	)
	submittal_by_name = {s.name: s for s in submittals}

	result = []
	for step in steps:
		revision = revision_by_name.get(step.submittal_revision)
		if not revision:
			continue
		submittal = submittal_by_name.get(revision.submittal)
		if not submittal or not frappe.has_permission("Project", "read", doc=submittal.project):
			continue
		result.append(
			{
				"step": step.name,
				"submittal": submittal.name,
				"submittal_number": submittal.submittal_number,
				"title": submittal.title,
				"project": submittal.project,
				"revision_label": revision.revision_label,
				"due_date": revision.due_date,
			}
		)
	return result
