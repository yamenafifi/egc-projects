"""Submittal lifecycle engine (see docs/ARCHITECTURE.md §2.5, docs/ARCHITECTURE_V2.md §7).

This module is the SINGLE place that computes or writes:

- `EGC Submittal`: `current_submission`, `current_submission_label`, `submittal_status`,
  `current_due_date`, `last_response_date`, `ball_in_court`.
- `EGC Submittal Revision`: `submission_status`, `response`, `response_date`, `responded_by`,
  `response_remarks` (post-insert), `ball_in_court_label`.
- `EGC Submittal Review Step`: `status`, `response`, `response_date`, `responded_by`,
  `response_remarks`.

A submittal identity accumulates submission/review cycles as history: `create_next_revision`
starts a new cycle, it never overwrites or copies forward an old one. Everything else — client
scripts, reports, other work packages — treats the fields above as read-only, system-derived
state. All writes below use `frappe.db.set_value`, which does not invoke controller hooks, so
the engine never re-enters itself. Mirrors `document_control.py`'s design throughout.

v2 addition — the multi-step review engine (§7) is ADDITIVE, not a replacement: a submission
with zero `EGC Submittal Review Step` rows behaves exactly as v1 — `submit()` leaves it
`Submitted`, and the top-level `record_response()` remains directly callable, unchanged. The
step machinery (`start_review`, `record_step_response`, stage evaluation) only ever activates
for a submission that actually has steps, so every v1 test in `test_submittal.py` keeps passing
against the exact same code paths it always exercised.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import today

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import document_control

#: Flag name checked by the submission controller's `on_update_after_submit` guard (and by
#: `validate` for pre-submit edits) to distinguish an engine-originated write from anything else,
#: e.g. a REST `PUT` that tries to fabricate a response directly.
ENGINE_FLAG = "egc_submittal_engine"

_ENGINE_GUARDED_FIELDS = (
	"submission_status",
	"response",
	"response_date",
	"responded_by",
	"response_remarks",
)


def next_submission_seq(submittal: str) -> int:
	"""The `submission_seq` for a new submission of `submittal`: max(existing) + 1."""
	max_seq = frappe.get_all(
		"EGC Submittal Revision",
		filters={"submittal": submittal},
		fields=[{"MAX": "submission_seq", "as": "max_seq"}],
	)[0].max_seq
	return (max_seq or 0) + 1


def get_governing_response_for_revision(document_revision: str) -> frappe._dict | None:
	"""The one fact `document_control.get_approval_status()` needs from this module: the latest
	non-cancelled submission that currently carries `document_revision`, if any.

	Owning this query here (not as a raw cross-doctype join written inline in Document Control)
	is what lets Documents stay primary and workflow-agnostic — Document Control asks a question
	instead of reaching into `EGC Submittal Revision`/`EGC Submittal Document Item`'s own shape
	itself. Returns `None` when the revision was never submitted through any submittal, or while
	the submittal doctypes don't exist yet (e.g. mid-install, before both work packages have run).
	"""
	if not frappe.db.table_exists("EGC Submittal Revision") or not frappe.db.table_exists(
		"EGC Submittal Document Item"
	):
		return None

	rows = frappe.get_all(
		"EGC Submittal Revision",
		filters=[
			["EGC Submittal Revision", "docstatus", "=", 1],
			["EGC Submittal Revision", "submission_status", "!=", c.SUBMISSION_CANCELLED],
			["EGC Submittal Document Item", "document_revision", "=", document_revision],
		],
		fields=["submission_status", "response", "submission_seq"],
		order_by="submission_seq desc",
		limit=1,
	)
	return rows[0] if rows else None


def suggest_next_revision_label(submittal: str) -> str:
	"""The system-suggested `revision_label` for a new submission of `submittal`.

	A purely numeric latest label (e.g. `00`, `01`) continues that zero-padded sequence;
	anything else (e.g. `A`, `B`) isn't ours to guess, so fall back to the next sequence
	number as a plain string.
	"""
	rows = frappe.get_all(
		"EGC Submittal Revision",
		filters={"submittal": submittal},
		fields=["revision_label"],
		order_by="submission_seq desc",
		limit=1,
	)
	if not rows:
		return "00"

	latest_label = (rows[0].revision_label or "").strip()
	if latest_label.isdigit():
		return str(int(latest_label) + 1).zfill(len(latest_label))
	return str(next_submission_seq(submittal))


def assert_engine_authorized(doc) -> None:
	"""Reject a change to any engine-written field that isn't the engine's own write.

	Called from the submission controller both pre-submit (`validate`, for an existing draft)
	and post-submit (`on_update_after_submit`). The engine itself never triggers this: it writes
	these fields with `frappe.db.set_value`, which does not run controller hooks at all.
	"""
	if frappe.flags.get(ENGINE_FLAG):
		return

	for fieldname in _ENGINE_GUARDED_FIELDS:
		if doc.has_value_changed(fieldname):
			frappe.throw(
				_("{0} is controlled by the submittal lifecycle engine and cannot be set directly.").format(
					_(doc.meta.get_label(fieldname))
				),
				title=_("Not Allowed"),
				exc=frappe.ValidationError,
			)


def _load_current_submission_row(submittal: str, exclude: str | None = None) -> "frappe._dict | None":
	filters = {"submittal": submittal, "submission_status": ("!=", c.SUBMISSION_CANCELLED)}
	if exclude:
		filters["name"] = ("!=", exclude)
	rows = frappe.get_all(
		"EGC Submittal Revision",
		filters=filters,
		fields=["name", "revision_label", "submission_status", "response", "due_date", "ball_in_court_label"],
		order_by="submission_seq desc",
		limit=1,
	)
	return rows[0] if rows else None


def get_current_submission(submittal: str) -> str | None:
	"""The current submission: highest `submission_seq` among non-Cancelled rows.

	A submission that has itself been cancelled naturally falls out of consideration, which is
	what lets a cancelled submission "restore" the previous Responded one as current, mirroring
	`document_control.get_current_revision`'s symmetry with cancellation.
	"""
	row = _load_current_submission_row(submittal)
	return row.name if row else None


def _latest_response_date(submittal: str, exclude: str | None = None):
	"""The most recent `response_date` across ALL non-cancelled, Responded submissions.

	Deliberately not scoped to the current submission: once `create_next_revision` opens a new
	Draft cycle, the current submission itself has no response yet, but "when did we last hear
	back on this submittal" is still meaningful history to surface.
	"""
	filters = {"submittal": submittal, "submission_status": c.SUBMISSION_RESPONDED}
	if exclude:
		filters["name"] = ("!=", exclude)
	rows = frappe.get_all(
		"EGC Submittal Revision",
		filters=filters,
		fields=["response_date"],
		order_by="submission_seq desc",
		limit=1,
	)
	return rows[0].response_date if rows else None


#: Responses that end a submission cycle with EGC itself now owing the next move (fix the
#: document, issue a new revision, resubmit) — as opposed to Approved/Approved with Comments,
#: where nobody owes anything further on this cycle.
_RESPONSES_NEEDING_EGC_ACTION = (c.RESPONSE_REJECTED, c.RESPONSE_REVISE_AND_RESUBMIT)


def _first_responsible_label(parent_doctype: str, parent_name: str) -> str | None:
	"""The display name of `parent_doctype`/`parent_name`'s "Responsible" assignee, if any.

	Deliberately a raw query, not `assignments.get_assignments_for` — this runs inside the
	engine's own state-recompute path (see `_refresh_from_current`), which can be reached from an
	external reviewer's session recording their response. That session may well lack read
	permission on `EGC Activity`; a permission-checked lookup here would crash the response
	recording itself over a fallback label, not just fail to find one.
	"""
	rows = frappe.get_all(
		"EGC Assignment",
		filters={"parent_doctype": parent_doctype, "parent_name": parent_name, "assignment_role": "Responsible"},
		fields=["person_label", "organization_type", "organization"],
		order_by="is_primary desc, creation asc",
		limit=1,
	)
	if not rows:
		return None
	if rows[0].person_label:
		return rows[0].person_label
	if rows[0].organization:
		name_field = "supplier_name" if rows[0].organization_type == "Supplier" else "customer_name"
		return frappe.db.get_value(rows[0].organization_type or "Customer", rows[0].organization, name_field)
	return None


def _needs_egc_action_ball_in_court(submittal: str) -> str | None:
	"""Who owns getting a Rejected/Revise & Resubmit submittal fixed and resubmitted — the
	Submittal's own Responsible assignee, falling back to any linked Activity's. Raw queries
	throughout, for the same permission-safety reason as `_first_responsible_label`."""
	label = _first_responsible_label("EGC Submittal", submittal)
	if label:
		return label

	activities = frappe.get_all(
		"EGC Activity Link",
		filters={"link_doctype": "EGC Submittal", "link_name": submittal},
		pluck="activity",
		order_by="creation asc",
	)
	for activity in activities:
		label = _first_responsible_label("EGC Activity", activity)
		if label:
			return label
	return None


def _refresh_from_current(submittal: str, exclude: str | None = None) -> None:
	current = _load_current_submission_row(submittal, exclude=exclude)
	if not current:
		state = {
			"current_submission": None,
			"current_submission_label": None,
			"submittal_status": c.SUBMISSION_DRAFT,
			"current_due_date": None,
			"last_response_date": None,
			"ball_in_court": None,
		}
	else:
		submittal_status = (
			current.response
			if current.submission_status == c.SUBMISSION_RESPONDED and current.response
			else current.submission_status
		)
		# Already computed onto the submission row by _refresh_ball_in_court whenever its
		# review-step state changes — copied up here, never recomputed independently, so there
		# is exactly one place that derives it from live step rows. EXCEPT: once every reviewer
		# is done and the answer was Rejected/Revise & Resubmit, that label goes empty (nobody's
		# still "In Review") even though the cycle isn't actually finished from EGC's side — the
		# ball just moved to whoever has to fix it. Only compute this fallback in that specific
		# gap, so it can never disagree with a genuinely live review step.
		ball_in_court = current.ball_in_court_label
		if not ball_in_court and current.submission_status == c.SUBMISSION_RESPONDED and current.response in _RESPONSES_NEEDING_EGC_ACTION:
			responsible = _needs_egc_action_ball_in_court(submittal)
			if responsible:
				ball_in_court = _("{0} — resubmission needed").format(responsible)

		state = {
			"current_submission": current.name,
			"current_submission_label": current.revision_label,
			"submittal_status": submittal_status,
			"current_due_date": current.due_date,
			"last_response_date": _latest_response_date(submittal, exclude=exclude),
			"ball_in_court": ball_in_court,
		}
	frappe.get_doc("EGC Submittal", submittal).db_set(state, update_modified=False)


def refresh_submittal_state(submittal: str) -> None:
	"""Recompute and write every `current_*`/`submittal_status`/`last_response_date` field.

	The sole writer of this state. Safe to call as often as needed — it is a pure recomputation
	from the submission rows currently in the database.
	"""
	_refresh_from_current(submittal)


def _engine_set_submission(name: str, values: dict) -> None:
	"""Write engine-owned fields on a submission without running controller hooks.

	`frappe.db.set_value` never triggers `on_update_after_submit`, so this can never re-enter
	`assert_engine_authorized`. The flag is still set/cleared around the call, per the engine's
	guard contract, in case a future write path here ever goes through `save()`.
	"""
	frappe.flags[ENGINE_FLAG] = True
	try:
		frappe.db.set_value("EGC Submittal Revision", name, values, update_modified=False)
	finally:
		frappe.flags[ENGINE_FLAG] = False


def _referenced_documents(doc) -> set[str]:
	documents = set()
	for row in doc.documents:
		document = row.document or frappe.db.get_value(
			"EGC Project Document Revision", row.document_revision, "document"
		)
		if document:
			documents.add(document)
	return documents


def _refresh_documents(doc) -> None:
	"""Refresh `approval_status` on every distinct document this submission carries.

	Required after ANY submittal-revision state change — submit, cancel, trash, response,
	under-review — so `EGC Project Document.approval_status` never drifts from the submission
	history that determines it.
	"""
	for document in _referenced_documents(doc):
		document_control.refresh_document_state(document)


def on_submission_submit(doc, method=None) -> None:
	_engine_set_submission(doc.name, {"submission_status": c.SUBMISSION_SUBMITTED, "date_submitted": today()})
	# Additive: a submission with no EGC Submittal Review Step rows has nothing for
	# start_review() to do, so this is a no-op for every v1-style submission and the
	# submission's own status stays Submitted, exactly as before this module grew steps.
	if _has_review_steps(doc.name):
		start_review(doc.name)
	refresh_submittal_state(doc.submittal)
	_refresh_documents(doc)

	submittal_manager = frappe.db.get_value("EGC Submittal", doc.submittal, "submittal_manager")
	if submittal_manager:
		from egc_projects.egc_projects import notifications

		notifications.notify_submission_received(doc.name, submittal_manager)


def on_submission_cancel(doc, method=None) -> None:
	_engine_set_submission(doc.name, {"submission_status": c.SUBMISSION_CANCELLED})
	_cancel_review_steps(doc.name)
	refresh_submittal_state(doc.submittal)
	_refresh_documents(doc)


def on_submission_trash(doc, method=None) -> None:
	"""Only a Draft (docstatus 0) submission may be deleted — review history is never erased.

	The framework already blocks deleting a submitted (docstatus 1) submission before
	`on_trash` runs; this asserts the same for a cancelled (docstatus 2) one, which the
	framework does not block by default. Uses `exclude` rather than `refresh_submittal_state`
	directly because this hook runs before the row is actually removed from the database.
	"""
	if doc.docstatus == 1:
		frappe.throw(
			_(
				"{0} is {1} and cannot be deleted. A submitted review cycle is history — cancel"
				" it instead if it was raised in error."
			).format(frappe.bold(doc.name), _(doc.submission_status)),
			title=_("Cannot Delete Submission"),
			exc=frappe.ValidationError,
		)

	# Same rule as document revisions: cancelling is the audited step, and only an
	# administrator may then purge, so a reviewer cannot erase a cycle by cancelling it first.
	if doc.docstatus == 2 and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only a System Manager may delete the cancelled submission {0}.").format(frappe.bold(doc.name)),
			title=_("Cannot Delete Submission"),
			exc=frappe.PermissionError,
		)

	# A Draft submission can still hold Pending review steps (a workflow template may be
	# applied before submit — apply_workflow_template/add_review_step both require docstatus 0),
	# which would otherwise reference a submittal_revision name that no longer exists.
	for step in frappe.get_all("EGC Submittal Review Step", filters={"submittal_revision": doc.name}, pluck="name"):
		frappe.delete_doc("EGC Submittal Review Step", step, ignore_permissions=True)

	documents = _referenced_documents(doc)
	_refresh_from_current(doc.submittal, exclude=doc.name)
	for document in documents:
		document_control.refresh_document_state(document)


@frappe.whitelist()
def mark_under_review(submission: str) -> None:
	doc = frappe.get_doc("EGC Submittal Revision", submission)
	frappe.has_permission("EGC Submittal Revision", "write", doc=doc, throw=True)

	if doc.docstatus != 1 or doc.submission_status != c.SUBMISSION_SUBMITTED:
		frappe.throw(
			_("{0} must be Submitted before it can be marked Under Review; it is currently {1}.").format(
				frappe.bold(doc.name), _(doc.submission_status)
			),
			title=_("Not Allowed"),
			exc=frappe.ValidationError,
		)

	_engine_set_submission(doc.name, {"submission_status": c.SUBMISSION_UNDER_REVIEW})
	refresh_submittal_state(doc.submittal)
	_refresh_documents(doc)


@frappe.whitelist()
def record_response(submission: str, response: str, remarks: str | None = None, response_date=None) -> None:
	doc = frappe.get_doc("EGC Submittal Revision", submission)
	frappe.has_permission("EGC Submittal Revision", "write", doc=doc, throw=True)

	if doc.docstatus != 1 or doc.submission_status not in c.SUBMISSION_OPEN_STATUSES:
		if doc.submission_status == c.SUBMISSION_RESPONDED:
			frappe.throw(
				_("{0} already has a response recorded. A response is history and cannot be re-recorded.").format(
					frappe.bold(doc.name)
				),
				title=_("Not Allowed"),
				exc=frappe.ValidationError,
			)
		frappe.throw(
			_("{0} must be Submitted or Under Review to record a response; it is currently {1}.").format(
				frappe.bold(doc.name), _(doc.submission_status)
			),
			title=_("Not Allowed"),
			exc=frappe.ValidationError,
		)

	if response not in c.REVIEW_RESPONSES:
		frappe.throw(
			_("{0} is not a valid review response.").format(frappe.bold(response)),
			title=_("Invalid Response"),
			exc=frappe.ValidationError,
		)

	# Shared with the v2 step engine's own stage-termination path (see
	# _apply_response_and_refresh, defined further down this file) — one function writes this
	# state and refreshes downstream documents, so the two entry points can never drift apart.
	_apply_response_and_refresh(doc, response, remarks, response_date)


@frappe.whitelist()
def create_next_revision(submittal: str) -> str:
	current_name = get_current_submission(submittal)
	if not current_name:
		frappe.throw(
			_("Submittal {0} has no submissions yet.").format(frappe.bold(submittal)),
			title=_("Not Allowed"),
			exc=frappe.ValidationError,
		)

	current = frappe.get_doc("EGC Submittal Revision", current_name)
	frappe.has_permission("EGC Submittal Revision", "write", doc=current, throw=True)
	frappe.has_permission("EGC Submittal Revision", "create", throw=True)

	if current.submission_status != c.SUBMISSION_RESPONDED:
		frappe.throw(
			_("A new submission can only be created after {0} has been Responded to; it is currently {1}.").format(
				frappe.bold(current.name), _(current.submission_status)
			),
			title=_("Not Allowed"),
			exc=frappe.ValidationError,
		)

	new_revision = frappe.get_doc(
		{
			"doctype": "EGC Submittal Revision",
			"submittal": submittal,
			"revision_label": suggest_next_revision_label(submittal),
		}
	)
	new_revision.insert()

	submittal_manager = frappe.db.get_value("EGC Submittal", submittal, "submittal_manager")
	if submittal_manager:
		from egc_projects.egc_projects import notifications

		notifications.notify_new_revision(submittal, new_revision.name, [submittal_manager])

	return new_revision.name


# ======================================================================================
# v2: multi-step review engine (docs/ARCHITECTURE_V2.md §7)
# ======================================================================================
#
# A submission's `EGC Submittal Review Step` rows model sequential-groups/parallel-groups with
# one integer column: steps sharing the same `sequence` are a parallel stage; the submission
# advances to the next distinct `sequence` only once every REQUIRED step at the current one has
# responded. A single Revise & Resubmit / Rejected response from ANY reviewer in the stage
# terminates the whole submission immediately with that response — standard construction
# submittal semantics: one reviewer sending it back stops the cycle, it does not wait for
# everyone else. An optional (not required) step still `In Review` when its stage clears is
# marked Skipped, not left dangling forever.

#: Flag distinguishing an engine-originated write on EGC Submittal Review Step from a direct
#: edit — mirrors ENGINE_FLAG above, kept separate so a bug in one guard can't mask the other.
STEP_ENGINE_FLAG = "egc_submittal_step_engine"

_STEP_TERMINAL_RESPONSES = (c.RESPONSE_REVISE_AND_RESUBMIT, c.RESPONSE_REJECTED)


def assert_step_engine_authorized(doc) -> None:
	if frappe.flags.get(STEP_ENGINE_FLAG):
		return
	for fieldname in (
		"status",
		"response",
		"response_date",
		"responded_by",
		"response_remarks",
		"response_attachment",
	):
		if doc.has_value_changed(fieldname):
			frappe.throw(
				_("{0} is controlled by the review workflow and cannot be set directly.").format(
					_(doc.meta.get_label(fieldname))
				),
				title=_("Not Allowed"),
				exc=frappe.ValidationError,
			)


def _engine_set_step(name: str, values: dict) -> None:
	frappe.flags[STEP_ENGINE_FLAG] = True
	try:
		frappe.db.set_value("EGC Submittal Review Step", name, values, update_modified=False)
	finally:
		frappe.flags[STEP_ENGINE_FLAG] = False


def _has_review_steps(submission: str) -> bool:
	return bool(frappe.db.exists("EGC Submittal Review Step", {"submittal_revision": submission}))


def _assign_step(step: str, reviewer_user: str, submission: str) -> None:
	from frappe.desk.form.assign_to import _add as assign_add

	label = frappe.db.get_value("EGC Submittal Revision", submission, "revision_label")
	assign_add(
		{
			"doctype": "EGC Submittal Review Step",
			"name": step,
			"assign_to": [reviewer_user],
			"description": _("Review required for submission {0}").format(label or submission),
		},
		ignore_permissions=True,
	)

	from egc_projects.egc_projects import notifications

	notifications.send_ball_in_court_email(reviewer_user, submission)


def _close_step_assignment(step: str, reviewer_user: str | None) -> None:
	if not reviewer_user:
		return
	from frappe.desk.form.assign_to import _remove as assign_remove

	try:
		assign_remove("EGC Submittal Review Step", step, reviewer_user)
	except frappe.DoesNotExistError:
		pass


def _refresh_ball_in_court(submission: str) -> None:
	"""Recomputes `ball_in_court_label` on the submission from its CURRENT `In Review` steps, then
	propagates it up to the parent Submittal's own `ball_in_court` (which is what the Hub's
	register column and detail-drawer header actually read).

	Never stored independently of this — a submission with no `In Review` steps (nothing open,
	or the step machinery was never used) gets a null label, matching the "derive, don't store"
	rule everywhere else in this app. The propagation step is not optional: without it, a
	mid-workflow stage transition (e.g. stage 0 responds and stage 1 opens) would leave the
	Submittal-level Ball in Court stuck on the PREVIOUS stage's reviewer until the submission's
	overall response finally resolves — `refresh_submittal_state` is otherwise only called from
	the terminal/lifecycle paths (submit, mark under review, response recorded, next revision),
	none of which fire on an intermediate stage advance.
	"""
	rows = frappe.get_all(
		"EGC Submittal Review Step",
		filters={"submittal_revision": submission, "status": c.STEP_IN_REVIEW},
		fields=["reviewer_user", "reviewer_role", "reviewer_label"],
		order_by="creation asc",
	)
	if not rows:
		label = None
	else:
		parts = []
		for row in rows:
			who = row.reviewer_label or row.reviewer_user or _("Unassigned")
			parts.append(f"{row.reviewer_role}: {who}" if row.reviewer_role else who)
		label = ", ".join(parts)

	_engine_set_submission(submission, {"ball_in_court_label": label})

	submittal = frappe.db.get_value("EGC Submittal Revision", submission, "submittal")
	if submittal:
		refresh_submittal_state(submittal)


@frappe.whitelist()
def get_ball_in_court(submission: str) -> dict:
	"""Live view of who must act next — never reads the stored label, so this is safe to call
	even mid-transition; `users`/`labels` are parallel lists, `is_external_only` is true when
	every current reviewer lacks a `reviewer_user` (nothing to notify in-app)."""
	rows = frappe.get_all(
		"EGC Submittal Review Step",
		filters={"submittal_revision": submission, "status": c.STEP_IN_REVIEW},
		fields=["reviewer_user", "reviewer_role", "reviewer_label"],
		order_by="creation asc",
	)
	return {
		"users": [row.reviewer_user for row in rows if row.reviewer_user],
		"labels": [row.reviewer_label or row.reviewer_user or "" for row in rows],
		"is_external_only": bool(rows) and not any(row.reviewer_user for row in rows),
	}


def start_review(submission: str) -> None:
	"""Marks every Pending step at the lowest pending `sequence` as In Review — the parallel
	stage that just opened — and assigns each such step's `reviewer_user` a ToDo, which is the
	actual notification delivery (§7: "reuse Frappe's own assignment mechanism")."""
	rows = frappe.get_all(
		"EGC Submittal Review Step",
		filters={"submittal_revision": submission, "status": c.STEP_PENDING},
		fields=["name", "sequence", "reviewer_user"],
		order_by="sequence asc",
	)
	if not rows:
		return

	lowest_sequence = rows[0].sequence
	for row in rows:
		if row.sequence != lowest_sequence:
			continue
		_engine_set_step(row.name, {"status": c.STEP_IN_REVIEW})
		if row.reviewer_user:
			_assign_step(row.name, row.reviewer_user, submission)

	_refresh_ball_in_court(submission)


def _cancel_review_steps(submission: str) -> None:
	rows = frappe.get_all(
		"EGC Submittal Review Step",
		filters={"submittal_revision": submission, "status": ("in", (c.STEP_PENDING, c.STEP_IN_REVIEW))},
		fields=["name", "reviewer_user", "status"],
	)
	for row in rows:
		if row.status == c.STEP_IN_REVIEW:
			_close_step_assignment(row.name, row.reviewer_user)
		_engine_set_step(row.name, {"status": c.STEP_SKIPPED})
	_refresh_ball_in_court(submission)


def _apply_response_and_refresh(submission_doc, response: str, remarks: str | None, response_date=None) -> None:
	"""The write+refresh tail shared by the top-level `record_response()` (unchanged v1 path)
	and the step engine's own stage-termination path — kept in one place so both routes stay in
	sync, without changing `record_response()`'s existing validation or call signature."""
	_engine_set_submission(
		submission_doc.name,
		{
			"submission_status": c.SUBMISSION_RESPONDED,
			"response": response,
			"response_date": response_date or today(),
			"responded_by": frappe.session.user,
			"response_remarks": remarks,
		},
	)
	refresh_submittal_state(submission_doc.submittal)
	_refresh_documents(submission_doc)

	submitted_by = frappe.db.get_value("EGC Submittal Revision", submission_doc.name, "submitted_by")
	submittal_manager = frappe.db.get_value("EGC Submittal", submission_doc.submittal, "submittal_manager")
	recipients = [u for u in (submitted_by, submittal_manager) if u]
	if recipients:
		from egc_projects.egc_projects import notifications

		notifications.notify_response_recorded(submission_doc.name, response, recipients)


@frappe.whitelist()
def apply_workflow_template(submission: str, template: str) -> list[str]:
	"""Instantiates `EGC Submittal Review Step` rows from `template`'s steps, resolving each
	`reviewer_role` to that submission's project via `project_profile.resolve_role_user()`.
	Copies data, not a live binding — editing the template later never touches steps already
	instantiated from it."""
	from egc_projects.egc_projects import project_profile

	doc = frappe.get_doc("EGC Submittal Revision", submission)
	frappe.has_permission("EGC Submittal Revision", "write", doc=doc, throw=True)

	if doc.docstatus != 0:
		frappe.throw(
			_("A workflow can only be applied to a Draft submission; {0} is {1}.").format(
				frappe.bold(doc.name), _(doc.submission_status)
			),
			exc=frappe.ValidationError,
		)
	if _has_review_steps(submission):
		frappe.throw(
			_("{0} already has review steps.").format(frappe.bold(doc.name)),
			title=_("Not Allowed"),
			exc=frappe.ValidationError,
		)

	template_doc = frappe.get_doc("EGC Submittal Workflow Template", template)
	created = []
	for row in template_doc.steps:
		reviewer_user = project_profile.resolve_role_user(doc.project, row.reviewer_role)
		stakeholders = project_profile.get_stakeholders(doc.project)
		reviewer_label = next(
			(s.party_name for s in stakeholders if s.role == row.reviewer_role), row.reviewer_role
		)
		step = frappe.get_doc(
			{
				"doctype": "EGC Submittal Review Step",
				"submittal_revision": submission,
				"sequence": row.sequence,
				"reviewer_role": row.reviewer_role,
				"reviewer_user": reviewer_user,
				"reviewer_label": row.label or reviewer_label,
				"is_required": row.is_required,
			}
		)
		step.insert()
		created.append(step.name)
	return created


@frappe.whitelist()
def add_review_step(
	submission: str,
	sequence: int,
	reviewer_role: str | None = None,
	reviewer_user: str | None = None,
	is_required: bool = True,
) -> str:
	"""Ad-hoc single-step addition, for a submission with no template."""
	doc = frappe.get_doc("EGC Submittal Revision", submission)
	frappe.has_permission("EGC Submittal Revision", "write", doc=doc, throw=True)

	if doc.docstatus != 0:
		frappe.throw(
			_("A review step can only be added to a Draft submission; {0} is {1}.").format(
				frappe.bold(doc.name), _(doc.submission_status)
			),
			exc=frappe.ValidationError,
		)

	label = None
	if reviewer_role and not reviewer_user:
		from egc_projects.egc_projects import project_profile

		reviewer_user = project_profile.resolve_role_user(doc.project, reviewer_role)
		stakeholders = project_profile.get_stakeholders(doc.project)
		label = next((s.party_name for s in stakeholders if s.role == reviewer_role), reviewer_role)

	step = frappe.get_doc(
		{
			"doctype": "EGC Submittal Review Step",
			"submittal_revision": submission,
			"sequence": sequence,
			"reviewer_role": reviewer_role,
			"reviewer_user": reviewer_user,
			"reviewer_label": label or reviewer_user,
			"is_required": is_required,
		}
	)
	step.insert()
	return step.name


@frappe.whitelist()
def remove_review_step(step: str) -> None:
	doc = frappe.get_doc("EGC Submittal Review Step", step)
	submission_doc = frappe.get_doc("EGC Submittal Revision", doc.submittal_revision)
	frappe.has_permission("EGC Submittal Revision", "write", doc=submission_doc, throw=True)

	if submission_doc.docstatus != 0:
		frappe.throw(
			_("Review steps can only be removed while the submission is still Draft."),
			exc=frappe.ValidationError,
		)
	frappe.delete_doc("EGC Submittal Review Step", step)


def _is_step_override_user() -> bool:
	roles = set(frappe.get_roles())
	return bool(roles & {"System Manager", c.ROLE_PROJECT_MANAGER, c.ROLE_DOCUMENT_CONTROLLER})


@frappe.whitelist()
def record_step_response(
	step: str, response: str, remarks: str | None = None, attachment: str | None = None
) -> None:
	"""Records ONE reviewer's response on their own step. Authorization here is identity-based,
	not doctype-role-based: the point of Ball in Court is that a specific person — who may be an
	external party holding no EGC role at all — is the one who must act, so the check is "are
	you that person" (or an internal override), not "do you hold role X"."""
	doc = frappe.get_doc("EGC Submittal Review Step", step)

	if not (frappe.session.user == doc.reviewer_user or _is_step_override_user()):
		frappe.throw(
			_("Only the assigned reviewer ({0}) may record this response.").format(
				doc.reviewer_label or doc.reviewer_user or _("Unassigned")
			),
			title=_("Not Permitted"),
			exc=frappe.PermissionError,
		)
	if doc.status != c.STEP_IN_REVIEW:
		frappe.throw(
			_("{0} is not currently under review; it is {1}.").format(frappe.bold(doc.name), _(doc.status)),
			title=_("Not Allowed"),
			exc=frappe.ValidationError,
		)
	if response not in c.REVIEW_RESPONSES:
		frappe.throw(
			_("{0} is not a valid review response.").format(frappe.bold(response)),
			title=_("Invalid Response"),
			exc=frappe.ValidationError,
		)

	_engine_set_step(
		doc.name,
		{
			"status": c.STEP_RESPONDED,
			"response": response,
			"response_date": today(),
			"responded_by": frappe.session.user,
			"response_remarks": remarks,
			"response_attachment": attachment,
		},
	)
	_close_step_assignment(doc.name, doc.reviewer_user)
	_evaluate_stage(doc.submittal_revision)


def _evaluate_stage(submission: str) -> None:
	"""Re-derives ball-in-court and, once every REQUIRED step at the current stage has
	responded, either terminates the submission (a Revise & Resubmit / Rejected response from
	ANY step wins immediately) or advances to the next stage / final aggregate response."""
	stage_rows = frappe.get_all(
		"EGC Submittal Review Step",
		filters={"submittal_revision": submission, "status": ("in", (c.STEP_IN_REVIEW, c.STEP_RESPONDED))},
		fields=["name", "status", "response", "is_required", "response_remarks"],
	)
	if not stage_rows:
		_refresh_ball_in_court(submission)
		return

	# Check for a terminating response FIRST, before asking whether every required step has
	# responded — a single Revise & Resubmit / Rejected wins immediately and must not wait on
	# siblings still In Review, terminal-response or not. Checking "is anything still open"
	# first would silently swallow this case: with two required reviewers at one stage, the
	# first one's Revise & Resubmit would sit inert until the second also responded, which
	# contradicts the whole point of a terminating response.
	responded = [r for r in stage_rows if r.status == c.STEP_RESPONDED]
	blocking = next((r for r in responded if r.response in _STEP_TERMINAL_RESPONSES), None)

	if blocking:
		# The cycle is over — every sibling still In Review (required or not) is Skipped, not
		# left open against a submission that has already been terminally responded to.
		for row in stage_rows:
			if row.status == c.STEP_IN_REVIEW:
				_close_step_assignment(row.name, frappe.db.get_value("EGC Submittal Review Step", row.name, "reviewer_user"))
				_engine_set_step(row.name, {"status": c.STEP_SKIPPED})
		submission_doc = frappe.get_doc("EGC Submittal Revision", submission)
		# The blocking reviewer's own remarks — not None. Without this, the SUBMISSION's own
		# `response_remarks` (what the Hub's "why" line reads) stayed permanently blank for every
		# step-based rejection, even though the exact same text was sitting right there on the
		# step row that caused it.
		_apply_response_and_refresh(submission_doc, blocking.response, remarks=blocking.response_remarks)
		_refresh_ball_in_court(submission)
		return

	required_still_open = [r for r in stage_rows if r.is_required and r.status == c.STEP_IN_REVIEW]
	if required_still_open:
		_refresh_ball_in_court(submission)
		return

	# The stage is settling — any optional step that never responded is Skipped, not left open.
	for row in stage_rows:
		if row.status == c.STEP_IN_REVIEW:
			_engine_set_step(row.name, {"status": c.STEP_SKIPPED})

	submission_doc = frappe.get_doc("EGC Submittal Revision", submission)

	next_pending = frappe.get_all(
		"EGC Submittal Review Step",
		filters={"submittal_revision": submission, "status": c.STEP_PENDING},
		fields=["name"],
		limit=1,
	)
	if next_pending:
		start_review(submission)
		return

	all_responses = frappe.get_all(
		"EGC Submittal Review Step",
		filters={"submittal_revision": submission, "status": c.STEP_RESPONDED},
		fields=["response"],
		pluck="response",
	)
	final = (
		c.RESPONSE_APPROVED
		if all_responses and all(r == c.RESPONSE_APPROVED for r in all_responses)
		else c.RESPONSE_APPROVED_WITH_COMMENTS
	)
	_apply_response_and_refresh(submission_doc, final, remarks=None)
	_refresh_ball_in_court(submission)
