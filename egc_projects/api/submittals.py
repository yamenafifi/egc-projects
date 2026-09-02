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

from egc_projects.egc_projects import assignments, relationships, submittal_control, validators

# --- add/remove a controlled document revision on a Draft submission --------------------------


@frappe.whitelist()
def add_submission_document(submission: str, document_revision: str) -> dict:
	"""Appends `document_revision` to a Draft submission's `documents` child table and saves —
	the proper path for mutating a child table (`frappe.client.insert` does not support
	inserting a standalone child row against an existing parent; the row must go through the
	parent document's own save cycle, which is what this does)."""
	doc = frappe.get_doc("EGC Submittal Revision", submission)
	frappe.has_permission("EGC Submittal Revision", "write", doc=doc, throw=True)

	if doc.docstatus != 0:
		frappe.throw(
			_("Documents can only be added while the submission is Draft; {0} is {1}.").format(
				frappe.bold(doc.name), _(doc.submission_status)
			),
			exc=frappe.ValidationError,
		)

	# The cross-submittal exclusivity check (a document revision can only be under review through
	# one submittal at a time) now lives in `EGCSubmittalRevision._validate_documents()` itself,
	# so it can't be bypassed by a direct `doc.append(...); doc.save()` elsewhere — it fires below
	# via this same `doc.save()`, not duplicated here.
	doc.append("documents", {"document_revision": document_revision})
	doc.save()
	return {"name": doc.name}


@frappe.whitelist()
def remove_submission_document(submission: str, row_name: str) -> dict:
	doc = frappe.get_doc("EGC Submittal Revision", submission)
	frappe.has_permission("EGC Submittal Revision", "write", doc=doc, throw=True)

	if doc.docstatus != 0:
		frappe.throw(
			_("Documents can only be removed while the submission is Draft; {0} is {1}.").format(
				frappe.bold(doc.name), _(doc.submission_status)
			),
			exc=frappe.ValidationError,
		)

	doc.documents = [row for row in doc.documents if row.name != row_name]
	doc.save()
	return {"name": doc.name}


# --- update_submission_dates (review/lead-time dates set at or after Start Submission) ---------

_DATE_FIELDS = (
	"due_date",
	"required_submission_date",
	"required_approval_date",
	"final_due_date",
	"required_on_site_date",
	"lead_time_days",
)


@frappe.whitelist()
def update_submission_dates(submission: str, **kwargs) -> dict:
	"""Sets whichever of the submission's plain review/lead-time date fields were provided.
	These are ordinary user-entered fields (see `egc_submittal_revision.json`) — none of them are
	engine-guarded like `submission_status`/`response`/etc. in `submittal_control.py`, and unlike
	those they're plain planning/reference data with no reason to freeze once the submission is
	no longer Draft (e.g. logging the "Required Approval Date" a client verbally committed to,
	after the package already went out). None of them carry `allow_on_submit` in the doctype, so
	a submitted doc needs `frappe.db.set_value` (bypasses the submit field-lock, same as
	`submittal_control.py`'s own engine writes) rather than `doc.save()`, which Frappe would
	reject outright."""
	doc = frappe.get_doc("EGC Submittal Revision", submission)
	frappe.has_permission("EGC Submittal Revision", "write", doc=doc, throw=True)

	values = {field: kwargs[field] for field in _DATE_FIELDS if kwargs.get(field) is not None}
	if not values:
		return {"name": doc.name}

	if doc.docstatus == 0:
		doc.update(values)
		doc.save()
	else:
		frappe.db.set_value("EGC Submittal Revision", submission, values, update_modified=False)
	return {"name": doc.name}


# --- create_first_submission -------------------------------------------------------------------


@frappe.whitelist()
def create_first_submission(submittal: str, revision_label: str = "00") -> dict:
	"""Creates the FIRST `EGC Submittal Revision` cycle for a Submittal that has none yet.

	Deliberately a separate function from `submittal_control.create_next_revision`, which is
	documented (docs/ARCHITECTURE_V2.md §7 / v1 §2.5) as "allowed only when the latest
	submission is Responded" — that contract stays exactly as written and tested; this covers
	the one case it explicitly does not (nothing exists yet), so a brand-new Submittal has a
	Hub-native path into its first cycle instead of only the native form.
	"""
	validators.require_project_permission(validators.get_project_of("EGC Submittal", submittal), "write")
	frappe.has_permission("EGC Submittal Revision", "create", throw=True)

	if frappe.db.exists("EGC Submittal Revision", {"submittal": submittal}):
		frappe.throw(
			_("{0} already has a submission. Use the current submission's own actions instead.").format(
				frappe.bold(submittal)
			),
			exc=frappe.ValidationError,
		)

	doc = frappe.get_doc({"doctype": "EGC Submittal Revision", "submittal": submittal, "revision_label": revision_label})
	doc.insert()
	return {"name": doc.name}


# --- submit_submission ---------------------------------------------------------------------


@frappe.whitelist()
def submit_submission(submission: str) -> dict:
	"""Submits a Draft `EGC Submittal Revision` — the only place this happens from the Hub,
	mirroring `api/documents.py`'s `submit_document_revision`. `on_submission_submit` (wired in
	hooks.py) is what actually moves the submission into review; this function is the thin,
	permission-checked entry point into that framework action."""
	if not submission or not frappe.db.exists("EGC Submittal Revision", submission):
		frappe.throw(_("Submission {0} not found.").format(submission), exc=frappe.DoesNotExistError)

	doc = frappe.get_doc("EGC Submittal Revision", submission)
	project = validators.get_project_of("EGC Submittal", doc.submittal)
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC Submittal Revision", "submit", doc=doc, throw=True)

	doc.submit()
	return {"name": doc.name, "submission_status": doc.submission_status}


# --- create_submittal ("+ New Submittal" from the Hub) ----------------------------------------

_CREATE_FIELDS = ("submittal_number", "title", "submittal_type", "discipline", "wbs_node", "description",
	"responsible_organization", "responsible_party", "received_from_person", "received_from",
	"submittal_manager", "specification_section")


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


# --- delete_submittal (Draft-only; submitted review history is permanent, no bypass) -----------


@frappe.whitelist()
def delete_submittal(submittal: str) -> None:
	"""Deletes a Submittal and every Draft revision it has — but only while EVERY revision is
	still Draft. The moment any revision has ever been submitted, this refuses outright: a
	submitted review cycle is history, and unlike a lone submission revision (which a System
	Manager may still purge after cancelling it, via the raw doctype form — see
	`submittal_control.on_submission_trash`), a Submittal that has real history is never
	deletable through this app's own workflow, for any role. There is deliberately no
	cancel-then-delete path here."""
	doc = frappe.get_doc("EGC Submittal", submittal)
	project = validators.get_project_of("EGC Submittal", submittal)
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC Submittal", "delete", doc=doc, throw=True)

	revisions = frappe.get_all("EGC Submittal Revision", filters={"submittal": submittal}, fields=["name", "docstatus"])
	if any(row.docstatus != 0 for row in revisions):
		frappe.throw(
			_(
				"{0} has submitted review history, which is permanent and cannot be deleted. Only a"
				" Draft submittal with no review history can be deleted."
			).format(frappe.bold(submittal)),
			title=_("Cannot Delete"),
			exc=frappe.ValidationError,
		)

	for row in revisions:
		frappe.delete_doc("EGC Submittal Revision", row.name, ignore_permissions=True)
	frappe.delete_doc("EGC Submittal", submittal, ignore_permissions=True)


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
	"responsible_organization",
	"responsible_party",
	"received_from_person",
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
	# Real datetimes (unlike the Date-only fields above) so the Hub's timeline can order events
	# that fall on the same day and attribute who started the cycle.
	"creation",
	"modified",
	"owner",
)

_STEP_FIELDS = (
	"name",
	"sequence",
	"reviewer_role",
	"reviewer_user",
	"reviewer_label",
	"is_required",
	"origin",
	"status",
	"response",
	"response_date",
	"responded_by",
	"response_remarks",
	"response_attachment",
	"creation",
	"modified",
)


def _submission_documents(submission: str) -> list[dict]:
	return frappe.get_all(
		"EGC Submittal Document Item",
		filters={"parent": submission},
		fields=["name", "document_revision", "document", "revision", "document_title"],
		order_by="idx asc",
	)


def _resolve_documents(document_names: list[str]) -> list[dict]:
	"""Live `EGC Project Document` identity + current revision for a set of document names —
	the single place both `_tracked_documents` (below) and the Hub's document-picker resolver
	go through, so "what's the current revision of this document" is never derived twice."""
	document_names = list(dict.fromkeys(document_names))
	if not document_names:
		return []
	return frappe.get_all(
		"EGC Project Document",
		filters={"name": ("in", document_names)},
		fields=[
			"name",
			"document_number",
			"title",
			"document_type",
			"current_revision",
			"current_revision_label",
			"document_status",
		],
		order_by="document_number asc",
	)


def _tracked_documents(latest_submission_documents: list[dict]) -> list[dict]:
	"""The distinct Documents the latest cycle is about, each resolved LIVE against
	`EGC Project Document` — not frozen to whatever that cycle actually attached. This is what
	lets the Hub say "this submittal is about M-101, latest issued revision is 02" even when the
	cycle in hand reviewed an older one, or a newer revision has since appeared."""
	document_names = [row.document for row in latest_submission_documents if row.document]
	return _resolve_documents(document_names)


@frappe.whitelist()
def get_documents_with_current_revision(project: str, documents) -> list[dict]:
	"""For each Document (picked by name, not revision), its live current Issued revision and
	identity fields. This is what lets the "Start Submission" dialog offer a plain Document
	picker instead of a Document Revision picker — nobody choosing what to submit for review
	should have to already know or hunt down a specific revision number; the current one is
	always what's meant. See SubmittalDetail.vue's `open_start_submission_dialog`."""
	if isinstance(documents, str):
		documents = frappe.parse_json(documents)
	validators.require_project_permission(project)
	return _resolve_documents(documents or [])


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
		# The document(s) the latest cycle is about, with each one's LIVE current revision — see
		# _tracked_documents. Empty when there's no submission cycle yet.
		"tracked_documents": _tracked_documents(submissions[0]["documents"] if submissions else []),
		# Reverse direction of EGC Activity Link — every Activity linked to this Submittal.
		"related_activities": relationships.get_activities_for("EGC Submittal", submittal),
		# Level 1 §31: multiple responsible people/organizations, beyond the single primary
		# responsible_organization/responsible_party pair.
		"assignments": assignments.get_assignments_for("EGC Submittal", submittal),
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


@frappe.whitelist()
def update_workflow_template(
	template: str, template_name: str | None = None, description: str | None = None, steps=None
) -> str:
	"""Full replace of `description`/`steps` — mirrors `create_workflow_template`'s own untyped
	`steps` handling. `template_name` is this doctype's `autoname: field:template_name` source,
	but that only sets `.name` at INSERT time — Frappe does not re-rename an existing document
	just because its autoname field changes on save, so a rename goes through `frappe.rename_doc`
	explicitly (which also syncs `template_name` itself to the new name). Editing or deleting a
	template never touches any already-instantiated `EGC Submittal Review Step` — those are
	copies made at `apply_workflow_template` time, never a live binding back to the template (see
	that function's own docstring), so this is always safe regardless of how many submissions
	already used this template."""
	frappe.has_permission("EGC Submittal Workflow Template", "write", throw=True)

	if template_name and template_name != template:
		template = frappe.rename_doc("EGC Submittal Workflow Template", template, template_name)

	doc = frappe.get_doc("EGC Submittal Workflow Template", template)
	if description is not None:
		doc.description = description
	if steps is not None:
		if isinstance(steps, str):
			steps = frappe.parse_json(steps)
		doc.set(
			"steps",
			[
				{
					"sequence": row.get("sequence"),
					"reviewer_role": row.get("reviewer_role"),
					"is_required": row.get("is_required", 1),
					"label": row.get("label"),
				}
				for row in steps
			],
		)
	doc.save()
	return doc.name


@frappe.whitelist()
def delete_workflow_template(template: str) -> None:
	frappe.has_permission("EGC Submittal Workflow Template", "delete", throw=True)
	frappe.delete_doc("EGC Submittal Workflow Template", template)


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
