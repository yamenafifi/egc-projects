"""Submittal lifecycle engine (see docs/ARCHITECTURE.md §2.5).

This module is the SINGLE place that computes or writes:

- `EGC Submittal`: `current_submission`, `current_submission_label`, `submittal_status`,
  `current_due_date`, `last_response_date`.
- `EGC Submittal Revision`: `submission_status`, `response`, `response_date`, `responded_by`,
  `response_remarks` (post-insert).

A submittal identity accumulates submission/review cycles as history: `create_next_revision`
starts a new cycle, it never overwrites or copies forward an old one. Everything else — client
scripts, reports, other work packages — treats the fields above as read-only, system-derived
state. All writes below use `frappe.db.set_value`, which does not invoke controller hooks, so
the engine never re-enters itself. Mirrors `document_control.py`'s design throughout.
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
		fields=["name", "revision_label", "submission_status", "response", "due_date"],
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


def _refresh_from_current(submittal: str, exclude: str | None = None) -> None:
	current = _load_current_submission_row(submittal, exclude=exclude)
	if not current:
		state = {
			"current_submission": None,
			"current_submission_label": None,
			"submittal_status": c.SUBMISSION_DRAFT,
			"current_due_date": None,
			"last_response_date": None,
		}
	else:
		submittal_status = (
			current.response
			if current.submission_status == c.SUBMISSION_RESPONDED and current.response
			else current.submission_status
		)
		state = {
			"current_submission": current.name,
			"current_submission_label": current.revision_label,
			"submittal_status": submittal_status,
			"current_due_date": current.due_date,
			"last_response_date": _latest_response_date(submittal, exclude=exclude),
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
	_engine_set_submission(doc.name, {"submission_status": c.SUBMISSION_SUBMITTED})
	refresh_submittal_state(doc.submittal)
	_refresh_documents(doc)


def on_submission_cancel(doc, method=None) -> None:
	_engine_set_submission(doc.name, {"submission_status": c.SUBMISSION_CANCELLED})
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

	_engine_set_submission(
		doc.name,
		{
			"submission_status": c.SUBMISSION_RESPONDED,
			"response": response,
			"response_date": response_date or today(),
			"responded_by": frappe.session.user,
			"response_remarks": remarks,
		},
	)
	refresh_submittal_state(doc.submittal)
	_refresh_documents(doc)


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
	return new_revision.name
