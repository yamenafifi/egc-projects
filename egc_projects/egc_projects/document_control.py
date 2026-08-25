"""Controlled-document lifecycle engine (see docs/ARCHITECTURE.md §2.4).

This module is the SINGLE place that computes or writes:

- `EGC Project Document`: `current_revision`, `current_revision_label`,
  `current_revision_date`, `current_file`, `document_status`, `approval_status`.
- `EGC Project Document Revision`: `revision_status`, `superseded_by` (post-insert).

Everything else — client scripts, reports, other work packages — treats these fields as
read-only, system-derived state. A revision that has been issued is never rewritten; a new
revision never destroys or inherits from an older one. All writes below use `frappe.db.set_value`
/ `Document.db_set`, which do not invoke controller hooks, so the engine never re-enters itself.
"""

from __future__ import annotations

import frappe
from frappe import _

from egc_projects.egc_projects import constants as c

#: Flag name checked by the revision controller's `on_update_after_submit` guard (and by
#: `validate` for pre-submit edits) to distinguish an engine-originated write from anything else,
#: e.g. a REST `PUT` that tries to rewrite `revision_status`/`superseded_by` directly.
ENGINE_FLAG = "egc_document_engine"

_REVISION_FIELDS = (
	"name",
	"revision",
	"revision_seq",
	"revision_status",
	"docstatus",
	"file",
	"revision_date",
	"issue_date",
)


def next_revision_seq(document: str) -> int:
	"""The `revision_seq` for a new revision of `document`: max(existing) + 1."""
	max_seq = frappe.get_all(
		"EGC Project Document Revision",
		filters={"document": document},
		fields=[{"MAX": "revision_seq", "as": "max_seq"}],
	)[0].max_seq
	return (max_seq or 0) + 1


def assert_engine_authorized(doc) -> None:
	"""Reject a change to `revision_status`/`superseded_by` that isn't the engine's own write.

	Called from the revision controller both pre-submit (`validate`, for an existing draft) and
	post-submit (`on_update_after_submit`). The engine itself never triggers this: it writes
	these fields with `frappe.db.set_value`, which does not run controller hooks at all.
	"""
	if frappe.flags.get(ENGINE_FLAG):
		return

	for fieldname in ("revision_status", "superseded_by"):
		if doc.has_value_changed(fieldname):
			frappe.throw(
				_("{0} is controlled by the document lifecycle engine and cannot be set directly.").format(
					_(doc.meta.get_label(fieldname))
				),
				title=_("Not Allowed"),
				exc=frappe.ValidationError,
			)


def get_current_revision(document: str) -> str | None:
	"""The current revision: highest `revision_seq` among submitted, Issued rows."""
	rows = frappe.get_all(
		"EGC Project Document Revision",
		filters={"document": document, "docstatus": 1, "revision_status": c.REVISION_ISSUED},
		fields=["name"],
		order_by="revision_seq desc",
		limit=1,
	)
	return rows[0].name if rows else None


def get_approval_status(document: str) -> str:
	"""Derive `approval_status` strictly from the current revision (the anti-conflict rule).

	A revision that is no longer current never contributes here, so a later revision never
	inherits an earlier one's approval. Degrades safely to `Not Submitted` while
	`EGC Submittal Revision` / `EGC Submittal Document Item` (built concurrently by another
	work package) do not exist yet.
	"""
	current_revision = get_current_revision(document)
	if not current_revision:
		return c.APPROVAL_NOT_SUBMITTED

	if not frappe.db.table_exists("EGC Submittal Revision") or not frappe.db.table_exists(
		"EGC Submittal Document Item"
	):
		return c.APPROVAL_NOT_SUBMITTED

	rows = frappe.get_all(
		"EGC Submittal Revision",
		filters=[
			["EGC Submittal Revision", "docstatus", "=", 1],
			["EGC Submittal Revision", "submission_status", "!=", c.SUBMISSION_CANCELLED],
			["EGC Submittal Document Item", "document_revision", "=", current_revision],
		],
		fields=["submission_status", "response", "submission_seq"],
		order_by="submission_seq desc",
		limit=1,
	)
	if not rows:
		return c.APPROVAL_NOT_SUBMITTED

	latest = rows[0]
	if latest.submission_status == c.SUBMISSION_RESPONDED:
		return latest.response or c.APPROVAL_NOT_SUBMITTED
	if latest.submission_status in c.SUBMISSION_OPEN_STATUSES:
		return c.APPROVAL_UNDER_REVIEW

	return c.APPROVAL_NOT_SUBMITTED


def _load_revisions(document: str, exclude: str | None = None) -> list[frappe._dict]:
	filters = {"document": document}
	if exclude:
		filters["name"] = ("!=", exclude)
	return frappe.get_all(
		"EGC Project Document Revision",
		filters=filters,
		fields=list(_REVISION_FIELDS),
		order_by="revision_seq desc",
	)


def _compute_document_state(revisions: list[frappe._dict]) -> dict:
	"""Derive `document_status` and the `current_*` fields from a revision list.

	`document_status`: `No Revision` when there are no revisions at all; `Draft` when revisions
	exist but none is issued; `Issued` when a current revision exists; `Cancelled` when
	revisions exist and every one of them is cancelled.
	"""
	if not revisions:
		return {
			"current_revision": None,
			"current_revision_label": None,
			"current_revision_date": None,
			"current_file": None,
			"document_status": c.DOCUMENT_NO_REVISION,
		}

	current = next(
		(r for r in revisions if r.docstatus == 1 and r.revision_status == c.REVISION_ISSUED), None
	)
	if current:
		document_status = c.DOCUMENT_ISSUED
	elif all(r.revision_status == c.REVISION_CANCELLED for r in revisions):
		document_status = c.DOCUMENT_CANCELLED
	else:
		document_status = c.DOCUMENT_DRAFT

	return {
		"current_revision": current.name if current else None,
		"current_revision_label": current.revision if current else None,
		"current_revision_date": current.revision_date if current else None,
		"current_file": current.file if current else None,
		"document_status": document_status,
	}


def _refresh_from_revisions(document: str, revisions: list[frappe._dict]) -> None:
	state = _compute_document_state(revisions)
	state["approval_status"] = (
		get_approval_status(document) if state["current_revision"] else c.APPROVAL_NOT_SUBMITTED
	)
	frappe.get_doc("EGC Project Document", document).db_set(state, update_modified=False)


def refresh_document_state(document: str) -> None:
	"""Recompute and write every `current_*`/`document_status`/`approval_status` field.

	The sole writer of this state. Safe to call as often as needed — it is a pure recomputation
	from the revision rows currently in the database.
	"""
	_refresh_from_revisions(document, _load_revisions(document))


def _engine_set_revision(name: str, values: dict) -> None:
	"""Write `revision_status`/`superseded_by` on a revision without running controller hooks.

	`frappe.db.set_value` never triggers `on_update_after_submit`, so this can never re-enter
	`assert_engine_authorized`. The flag is still set/cleared around the call, per the
	architecture's guard contract, in case a future write path here ever goes through `save()`.
	"""
	frappe.flags[ENGINE_FLAG] = True
	try:
		frappe.db.set_value("EGC Project Document Revision", name, values, update_modified=False)
	finally:
		frappe.flags[ENGINE_FLAG] = False


def _recompute_revision_statuses(document: str) -> None:
	"""Re-derive `revision_status`/`superseded_by` for every submitted revision of `document`.

	Pure function of the submitted (docstatus=1) rows: the highest `revision_seq` among them is
	Issued with no `superseded_by`; every other one is Superseded, pointing at that same current
	revision. Draft (docstatus 0) and Cancelled (docstatus 2) rows are terminal states and are
	never touched here.

	Because this only ever looks at the *current* set of docstatus=1 rows, it handles every case
	uniformly with no special-casing:
	- a normal submit demotes the previous current revision;
	- an out-of-order submit (a lower `revision_seq` submitted after a higher one is already
	  current) demotes itself immediately instead of the existing current revision;
	- a cancel of the current revision naturally "restores" the next-highest submitted revision
	  to Issued, since it is now the highest remaining docstatus=1 row.
	"""
	rows = frappe.get_all(
		"EGC Project Document Revision",
		filters={"document": document, "docstatus": 1},
		fields=["name", "revision_seq", "revision_status", "superseded_by"],
		order_by="revision_seq desc",
	)
	if not rows:
		return

	current = rows[0]
	if current.revision_status != c.REVISION_ISSUED or current.superseded_by:
		_engine_set_revision(current.name, {"revision_status": c.REVISION_ISSUED, "superseded_by": None})

	for row in rows[1:]:
		if row.revision_status != c.REVISION_SUPERSEDED or row.superseded_by != current.name:
			_engine_set_revision(
				row.name, {"revision_status": c.REVISION_SUPERSEDED, "superseded_by": current.name}
			)


def on_revision_submit(doc, method=None) -> None:
	_recompute_revision_statuses(doc.document)
	refresh_document_state(doc.document)


def on_revision_cancel(doc, method=None) -> None:
	_engine_set_revision(doc.name, {"revision_status": c.REVISION_CANCELLED, "superseded_by": None})
	_recompute_revision_statuses(doc.document)
	refresh_document_state(doc.document)


def on_revision_trash(doc, method=None) -> None:
	"""Guard deletion so an issued revision can never be quietly erased.

	- Draft (docstatus 0): deletable by anyone who can delete the doctype. Nothing was issued.
	- Issued/Superseded (docstatus 1): never deletable. The framework blocks this before
	  `on_trash` even runs; the explicit check documents the rule and covers any path that
	  reaches here another way.
	- Cancelled (docstatus 2): deletable by a System Manager only. The framework would allow
	  anyone to delete a cancelled document, which would let a document controller erase a
	  revision by cancelling it first. Requiring cancellation *and* an administrator keeps a
	  purge deliberate and auditable, while still leaving a real escape hatch for genuine
	  mistakes and for test data — a record no one can ever remove is its own liability.
	"""
	if doc.docstatus == 1:
		frappe.throw(
			_(
				"{0} is {1} and cannot be deleted. An issued revision is history — cancel it"
				" instead if it was raised in error."
			).format(frappe.bold(doc.name), _(doc.revision_status)),
			title=_("Cannot Delete Revision"),
			exc=frappe.ValidationError,
		)

	if doc.docstatus == 2 and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only a System Manager may delete the cancelled revision {0}.").format(frappe.bold(doc.name)),
			title=_("Cannot Delete Revision"),
			exc=frappe.PermissionError,
		)

	_refresh_from_revisions(doc.document, _load_revisions(doc.document, exclude=doc.name))
