"""Whitelisted API behind the Hub's Documents tab (docs/ARCHITECTURE_V2.md §0 finding 4, §12).

Every `EGC Project Document` for a project, not filtered to drawings — `api/hub.py`'s
`get_drawings` remains the drawing-only register; this module is what gives a non-drawing
controlled document (Method Statement, Specification, Calculation, ...) a home in the Hub at
all. Follows `api/hub.py`'s conventions verbatim: `validators.require_project_permission` first,
a per-endpoint filter allow-list, `frappe.get_all` only, no raw SQL. This module owns no business
state — `current_revision_label`/`document_status`/`approval_status` are `document_control.py`'s;
this module only ever reads them.
"""

from __future__ import annotations

import frappe
from frappe import _

from egc_projects.egc_projects import constants as c, relationships, validators
from egc_projects.egc_projects.doctype.egc_project_document import egc_project_document


# --- filter handling ---------------------------------------------------------------------------
# Kept local rather than imported from `api/hub.py`: several packages are adding their own
# `api/*.py` module this wave, each with its own filter allow-list, and none of them should
# depend on another agent's file changing shape mid-wave (docs/ARCHITECTURE_V2.md §12).


def _parse_filters(filters) -> dict:
	if not filters:
		return {}
	if isinstance(filters, str):
		filters = frappe.parse_json(filters)
	if not isinstance(filters, dict):
		frappe.throw(_("Filters must be a JSON object."), exc=frappe.ValidationError)
	return filters


def _validated_filters(filters, allowed: set[str]) -> dict:
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


# --- get_documents -------------------------------------------------------------------------------

_DOCUMENT_FILTER_FIELDS = {"document_type", "discipline", "approval_status", "document_status"}

_DOCUMENT_LIST_FIELDS = (
	"name as document",
	"document_number",
	"title",
	"document_type",
	"discipline",
	"current_revision",
	"current_revision_label",
	"document_status",
	"approval_status",
	"originator",
	"current_revision_date",
	"current_file",
	# Drawing-only fields — meaningless on a non-drawing document, but harmless to always fetch;
	# lets the Hub's "Drawings only" toggle filter without a second round trip. See
	# get_drawing_document_types() below for what actually counts as a drawing.
	"drawing_set",
	"drawing_area",
)


@frappe.whitelist()
def get_documents(project: str, filters=None) -> list[dict]:
	"""Every controlled document of `project`, regardless of `document_type.is_drawing`.

	This is the whole point of the tab: `api/hub.py.get_drawings` only ever surfaces documents
	whose type is flagged `is_drawing = 1`, so a Method Statement or Specification has never had
	a register of its own until this endpoint.
	"""
	validators.require_project_permission(project)

	query_filters = _validated_filters(filters, _DOCUMENT_FILTER_FIELDS)
	query_filters["project"] = project

	rows = frappe.get_all(
		"EGC Project Document",
		filters=query_filters,
		fields=list(_DOCUMENT_LIST_FIELDS),
		order_by="document_number asc",
	)
	governing = _governing_submittal_info(rows)
	for row in rows:
		info = governing.get(row.document)
		row["governing_submittal"] = info.submittal_number if info else None
		row["ball_in_court"] = info.ball_in_court if info else None
		row["submittal_due_date"] = info.current_due_date if info else None
	return rows


def _governing_submittal_info(document_rows: list[dict]) -> dict[str, frappe._dict]:
	"""Batched (one round trip regardless of row count, mirroring `api/hub.py.get_activities()`'s
	`_wbs_labels()` pattern): for every document row with a current revision, the Submittal that
	currently governs its approval status — same "latest non-cancelled submission carrying this
	revision" rule as `submittal_control.get_governing_response_for_revision()`, extended to
	return which Submittal it is (not just its response), so the register can show inline who
	owes the next action without a second round trip per row. Three simple queries rather than
	one join-and-project query — Frappe's `get_all` field-selection-from-a-joined-child-table
	syntax is finicky to get right; three plain queries stay obviously correct.
	"""
	revision_to_document = {row.current_revision: row.document for row in document_rows if row.get("current_revision")}
	if not revision_to_document:
		return {}
	if not frappe.db.table_exists("EGC Submittal Revision") or not frappe.db.table_exists("EGC Submittal Document Item"):
		return {}

	item_rows = frappe.get_all(
		"EGC Submittal Document Item",
		filters={"document_revision": ("in", list(revision_to_document))},
		fields=["document_revision", "parent as submission"],
	)
	if not item_rows:
		return {}

	submission_rows = frappe.get_all(
		"EGC Submittal Revision",
		filters={
			"name": ("in", [r.submission for r in item_rows]),
			"docstatus": 1,
			"submission_status": ("!=", c.SUBMISSION_CANCELLED),
		},
		fields=["name", "submittal", "submission_seq"],
	)
	submission_by_name = {r.name: r for r in submission_rows}

	# Latest (highest submission_seq) non-cancelled submission per document_revision — same
	# "anti-conflict" rule document_control.get_approval_status() applies.
	governing_submittal_by_revision = {}
	for item in item_rows:
		submission = submission_by_name.get(item.submission)
		if not submission:
			continue
		current = governing_submittal_by_revision.get(item.document_revision)
		if not current or submission.submission_seq > current.submission_seq:
			governing_submittal_by_revision[item.document_revision] = submission

	submittal_names = {s.submittal for s in governing_submittal_by_revision.values()}
	if not submittal_names:
		return {}
	submittals = {
		s.name: s
		for s in frappe.get_all(
			"EGC Submittal",
			filters={"name": ("in", list(submittal_names))},
			fields=["name", "submittal_number", "ball_in_court", "current_due_date"],
		)
	}

	result = {}
	for revision, document_name in revision_to_document.items():
		submission = governing_submittal_by_revision.get(revision)
		if submission and submission.submittal in submittals:
			result[document_name] = submittals[submission.submittal]
	return result


@frappe.whitelist()
def get_drawing_document_types() -> list[str]:
	"""Every `EGC Document Type` flagged as a drawing type — what the Hub's Documents tab uses
	for its "Drawings only" filter (a Drawing is not a separate record, just a Document whose
	type is flagged this way). Reuses `api/hub.py`'s own definition rather than a second one, so
	the two can never drift apart."""
	from egc_projects.api.hub import get_drawing_document_types as _get_drawing_document_types

	return _get_drawing_document_types()


# --- get_document_detail -------------------------------------------------------------------------

_DOCUMENT_DETAIL_FIELDS = (
	"name",
	"project",
	"document_number",
	"title",
	"document_type",
	"discipline",
	"originator",
	"originator_person",
	"wbs_node",
	"description",
	"drawing_set",
	"drawing_area",
	"drawing_date",
	"received_date",
	"current_revision",
	"current_revision_label",
	"current_revision_date",
	"current_file",
	"document_status",
	"approval_status",
)


def _document_dict(name: str) -> dict:
	row = frappe.db.get_value("EGC Project Document", name, _DOCUMENT_DETAIL_FIELDS, as_dict=True)
	row["is_drawing"] = bool(frappe.db.get_value("EGC Document Type", row.document_type, "is_drawing"))
	return row


def _related_submittals(document: str) -> list[dict]:
	"""Every Submittal that has EVER carried any revision of `document`, current or superseded.

	Walks every revision of the document -> every `EGC Submittal Document Item` row referencing
	one of them -> that row's parent `EGC Submittal Revision` -> that submission's `EGC
	Submittal`. A submission row is never rewritten once submitted, so this naturally surfaces
	review cycles that carried a now-superseded revision, not only ones tied to the current one.
	"""
	revision_names = frappe.get_all("EGC Project Document Revision", filters={"document": document}, pluck="name")
	if not revision_names:
		return []

	item_rows = frappe.get_all(
		"EGC Submittal Document Item",
		filters={"document_revision": ("in", revision_names)},
		fields=["parent as submittal_revision"],
	)
	if not item_rows:
		return []

	submission_rows = frappe.get_all(
		"EGC Submittal Revision",
		filters={"name": ("in", list({row.submittal_revision for row in item_rows}))},
		fields=[
			"name",
			"submittal",
			"revision_label",
			"submission_status",
			"response",
			"response_remarks",
			"date_submitted",
			"due_date",
			# Real Datetimes (unlike date_submitted/due_date, Date-only) — `creation` anchors the
			# "submitted for review" timeline event, `modified` is the best available proxy for
			# "when the response was recorded" (this endpoint doesn't join into the step engine),
			# needed so DocumentDetail.vue's unified timeline can interleave these against
			# revision events and comments in real chronological order.
			"creation",
			"modified",
		],
		order_by="submission_seq desc",
	)
	if not submission_rows:
		return []

	submittals = {
		row.name: row
		for row in frappe.get_all(
			"EGC Submittal",
			filters={"name": ("in", list({row.submittal for row in submission_rows}))},
			fields=["name", "submittal_number", "title", "submittal_status", "ball_in_court"],
		)
	}

	result = []
	for row in submission_rows:
		submittal = submittals.get(row.submittal)
		if not submittal:
			continue
		result.append(
			{
				"submittal": submittal.name,
				"submittal_number": submittal.submittal_number,
				"submittal_title": submittal.title,
				"submittal_status": submittal.submittal_status,
				"ball_in_court": submittal.ball_in_court,
				"submittal_revision": row.name,
				"revision_label": row.revision_label,
				"submission_status": row.submission_status,
				"response": row.response,
				"response_remarks": row.response_remarks,
				"date_submitted": row.date_submitted,
				"due_date": row.due_date,
				"creation": row.creation,
				"modified": row.modified,
			}
		)
	return result


@frappe.whitelist()
def get_document_detail(document: str) -> dict:
	if not document or not frappe.db.exists("EGC Project Document", document):
		frappe.throw(_("Document {0} not found.").format(document), exc=frappe.DoesNotExistError)

	project = validators.get_project_of("EGC Project Document", document)
	validators.require_project_permission(project)

	return {
		"document": _document_dict(document),
		# Reuses the doctype's own whitelisted method rather than re-querying revisions here —
		# it is already exactly the shape `egc_project_document.js` renders on the native form.
		"revisions": egc_project_document.get_revisions(document),
		"activities": relationships.get_activities_for("EGC Project Document", document),
		"submittals": _related_submittals(document),
	}


# --- create_document -----------------------------------------------------------------------------


@frappe.whitelist()
def create_document(
	project: str,
	document_number: str,
	title: str,
	document_type: str,
	discipline: str | None = None,
	originator: str | None = None,
	originator_person: str | None = None,
	wbs_node: str | None = None,
	description: str | None = None,
	drawing_set: str | None = None,
	drawing_area: str | None = None,
	drawing_date: str | None = None,
	received_date: str | None = None,
) -> dict:
	# Two gates, deliberately: `require_project_permission` proves the caller may act on this
	# Project at all; `has_permission("create")` proves they specifically hold one of the EGC
	# roles that may author a controlled document (docs/ARCHITECTURE.md §4 — EGC roles are
	# additive to, not a substitute for, the core Project permission).
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC Project Document", "create", throw=True)

	doc = frappe.get_doc(
		{
			"doctype": "EGC Project Document",
			"project": project,
			"document_number": document_number,
			"title": title,
			"document_type": document_type,
			"discipline": discipline,
			"originator": originator,
			"originator_person": originator_person,
			"wbs_node": wbs_node,
			"description": description,
			"drawing_set": drawing_set,
			"drawing_area": drawing_area,
			"drawing_date": drawing_date,
			"received_date": received_date,
		}
	)
	doc.insert()
	return _document_dict(doc.name)


# --- create_document_revision ---------------------------------------------------------------------

_REVISION_FIELDS = (
	"name",
	"document",
	"project",
	"revision",
	"revision_seq",
	"file",
	"native_file",
	"revision_date",
	"issue_date",
	"revision_status",
	"superseded_by",
	"reason_for_revision",
	"remarks",
	"readiness",
	"docstatus",
)


def _revision_dict(name: str) -> dict:
	return frappe.db.get_value("EGC Project Document Revision", name, _REVISION_FIELDS, as_dict=True)


@frappe.whitelist()
def create_document_revision(
	document: str,
	revision: str,
	file: str,
	native_file: str | None = None,
	revision_date: str | None = None,
	reason_for_revision: str | None = None,
	remarks: str | None = None,
	readiness: str | None = None,
) -> dict:
	"""Insert a Draft revision. Never submits it — issuing is a separate, deliberate action.

	Mirrors the existing "New Revision" flow already on the native `EGC Project Document
	Revision` form; this is the same capability surfaced inside the Hub, not a new semantics.

	`native_file` is the paired authoring file for a Drawing (e.g. a .dwg alongside `file`'s
	.pdf) — same revision, two attachments, per direct user request. Meaningless for a
	non-drawing document; the Hub only ever shows the field when the document's type is a
	drawing type, but nothing here enforces that server-side since a non-drawing document
	genuinely having a native CAD source file too is a harmless, plausible edge case, not a
	violation of any invariant.
	"""
	if not document or not frappe.db.exists("EGC Project Document", document):
		frappe.throw(_("Document {0} not found.").format(document), exc=frappe.DoesNotExistError)

	project = validators.get_project_of("EGC Project Document", document)
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC Project Document Revision", "create", throw=True)

	values = {
		"doctype": "EGC Project Document Revision",
		"document": document,
		"revision": revision,
		"file": file,
		"native_file": native_file,
		"reason_for_revision": reason_for_revision,
		"remarks": remarks,
	}
	if readiness:
		values["readiness"] = readiness
	# Omit entirely rather than pass `None` when the caller didn't supply one — the field's own
	# `default: "Today"` only applies when the key is absent, not when it is present and empty.
	if revision_date:
		values["revision_date"] = revision_date

	doc = frappe.get_doc(values)
	doc.insert()
	return _revision_dict(doc.name)


# --- update_revision_readiness ------------------------------------------------------------------

_READINESS_VALUES = ("Uploaded", "Reviewed", "Ready to Publish")


@frappe.whitelist()
def update_revision_readiness(revision: str, readiness: str) -> dict:
	"""Move a Draft revision through its internal pre-issue review state
	(docs/ARCHITECTURE_V2.md §9). Purely informational metadata — `readiness` introduces no new
	lifecycle state and does not touch `revision_status`; issuing is still, and only, `submit()`.
	`readiness` is not `allow_on_submit`, so the framework itself refuses this once the revision
	is Issued — this endpoint only ever reaches a Draft row in practice, but is guarded anyway."""
	if not revision or not frappe.db.exists("EGC Project Document Revision", revision):
		frappe.throw(_("Revision {0} not found.").format(revision), exc=frappe.DoesNotExistError)
	if readiness not in _READINESS_VALUES:
		frappe.throw(_("{0} is not a valid readiness value.").format(frappe.bold(readiness)), exc=frappe.ValidationError)

	doc = frappe.get_doc("EGC Project Document Revision", revision)
	project = validators.get_project_of("EGC Project Document", doc.document)
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC Project Document Revision", "write", doc=doc, throw=True)

	if doc.docstatus != 0:
		frappe.throw(
			_("Readiness can only be changed while the revision is Draft; {0} is {1}.").format(
				frappe.bold(doc.name), _(doc.revision_status)
			),
			exc=frappe.ValidationError,
		)

	doc.readiness = readiness
	doc.save()
	return _revision_dict(doc.name)


# --- submit_document_revision ---------------------------------------------------------------------


@frappe.whitelist()
def submit_document_revision(revision: str) -> dict:
	"""Issue a revision. The ONLY place a revision becomes Issued — irreversible by design.

	Once submitted, `file` is not `allow_on_submit` (docs/ARCHITECTURE.md §2.4), so the framework
	itself refuses to let this revision's file ever change again. The caller-facing UI must make
	that permanence unmistakable before calling this.
	"""
	if not revision or not frappe.db.exists("EGC Project Document Revision", revision):
		frappe.throw(_("Revision {0} not found.").format(revision), exc=frappe.DoesNotExistError)

	document = frappe.db.get_value("EGC Project Document Revision", revision, "document")
	project = validators.get_project_of("EGC Project Document", document)
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC Project Document Revision", "submit", doc=revision, throw=True)

	doc = frappe.get_doc("EGC Project Document Revision", revision)
	doc.submit()
	return _revision_dict(doc.name)
