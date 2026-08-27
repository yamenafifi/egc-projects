"""Whitelisted API behind the Hub's WBS tab (v1 §2.2 for the tree itself; the operational
upgrade — rollups, reorder, copy, bulk create — is this upgrade's own addition, since
docs/ARCHITECTURE_V2.md does not carry a dedicated WBS section beyond the audit finding that the
v1 tree was a label list, not a project-control summary).

Follows `api/documents.py`'s conventions verbatim: `validators.require_project_permission`
first, `frappe.get_all` only, no raw SQL. No new field is ever added to `EGC WBS Node` to hold a
rollup value — every number in `get_wbs_summary` is computed fresh from Activities/Documents/
Submittals on each call, exactly like `document_control.py`'s own "derive, don't store" rule.

Rollup semantics: every metric aggregates over a node's WHOLE subtree, not just its direct
children. A WBS node with nothing directly tagged against it (very common for a group node like
"Mechanical", whose Activities are tagged against its descendant "HVAC" instead) would otherwise
show blank/zero at every level except the leaves, which defeats the point of a WBS
project-control summary — a subtree-wide progress figure is a coherent, useful number at any
level of the tree, while a direct-children-only one is not.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, getdate, today

from egc_projects.egc_projects import validators
from egc_projects.egc_projects.doctype.egc_activity.egc_activity import is_overdue as activity_is_overdue

# --- get_wbs_summary -------------------------------------------------------------------------

_NODE_FIELDS = (
	"name",
	"wbs_code",
	"wbs_name",
	"parent_egc_wbs_node as parent",
	"is_group",
	"sequence",
	"status",
	"discipline",
	"lft",
	"rgt",
)


def _ancestor_map(nodes: list[dict]) -> dict[str, list[str]]:
	"""`wbs_node name -> [itself, its parent, its grandparent, ...]`, via NestedSet containment.

	A node A is an ancestor-or-self of B exactly when `A.lft <= B.lft and A.rgt >= B.rgt`. One
	O(n²) pass over a project's WBS nodes — deliberately simple, matching the same "these graphs
	are small, a plain Python walk beats anything cleverer" call made for Activity Dependency's
	cycle check (docs/ARCHITECTURE_V2.md §6).
	"""
	result: dict[str, list[str]] = {}
	for node in nodes:
		result[node.name] = [
			other.name for other in nodes if other.lft <= node.lft and other.rgt >= node.rgt
		]
	return result


def _get_drawing_document_types() -> list[str]:
	from egc_projects.api.hub import get_drawing_document_types

	return get_drawing_document_types()


@frappe.whitelist()
def get_wbs_summary(project: str) -> list[dict]:
	validators.require_project_permission(project)

	nodes = frappe.get_all("EGC WBS Node", filters={"project": project}, fields=list(_NODE_FIELDS), order_by="lft asc")
	if not nodes:
		return []

	ancestors = _ancestor_map(nodes)

	totals = {
		node.name: {
			"activity_total": 0,
			"activity_completed": 0,
			"percent_sum": 0.0,
			"percent_count": 0,
			"activity_overdue_count": 0,
			"planned_start": None,
			"planned_finish": None,
			"document_count": 0,
			"drawing_count": 0,
			"submittal_open_count": 0,
			"submittal_overdue_count": 0,
		}
		for node in nodes
	}

	activities = frappe.get_all(
		"EGC Activity",
		filters={"project": project, "wbs_node": ("is", "set")},
		fields=["wbs_node", "status", "percent_complete", "planned_start_date", "planned_end_date"],
	)
	for activity in activities:
		for ancestor in ancestors.get(activity.wbs_node, []):
			bucket = totals[ancestor]
			bucket["activity_total"] += 1
			if activity.status == "Completed":
				bucket["activity_completed"] += 1
			bucket["percent_sum"] += flt(activity.percent_complete)
			bucket["percent_count"] += 1
			if activity_is_overdue(activity.status, activity.planned_end_date):
				bucket["activity_overdue_count"] += 1
			if activity.planned_start_date:
				candidates = [d for d in (bucket["planned_start"], activity.planned_start_date) if d]
				bucket["planned_start"] = min(candidates) if candidates else None
			if activity.planned_end_date:
				candidates = [d for d in (bucket["planned_finish"], activity.planned_end_date) if d]
				bucket["planned_finish"] = max(candidates) if candidates else None

	# One query for every Document under this project, not just Drawings — §29's rollup list
	# names "Submittals" and "Documents" as two distinct figures; Drawings is a subset of
	# Documents (`EGC Document Type.is_drawing`), not a stand-in for the whole count.
	drawing_types = set(_get_drawing_document_types())
	documents = frappe.get_all(
		"EGC Project Document",
		filters={"project": project, "wbs_node": ("is", "set")},
		fields=["wbs_node", "document_type"],
	)
	for document in documents:
		for ancestor in ancestors.get(document.wbs_node, []):
			totals[ancestor]["document_count"] += 1
			if document.document_type in drawing_types:
				totals[ancestor]["drawing_count"] += 1

	submittals = frappe.get_all(
		"EGC Submittal",
		filters={"project": project, "wbs_node": ("is", "set")},
		fields=["wbs_node", "submittal_status", "current_due_date"],
	)
	today_date = getdate(today())
	for submittal in submittals:
		if submittal.submittal_status not in ("Submitted", "Under Review"):
			continue
		for ancestor in ancestors.get(submittal.wbs_node, []):
			bucket = totals[ancestor]
			bucket["submittal_open_count"] += 1
			if submittal.current_due_date and getdate(submittal.current_due_date) < today_date:
				bucket["submittal_overdue_count"] += 1

	result = []
	for node in nodes:
		bucket = totals[node.name]
		result.append(
			{
				"name": node.name,
				"wbs_code": node.wbs_code,
				"wbs_name": node.wbs_name,
				"parent": node.parent,
				"is_group": node.is_group,
				"sequence": node.sequence,
				"status": node.status,
				"discipline": node.discipline,
				"activity_total": bucket["activity_total"],
				"activity_completed": bucket["activity_completed"],
				"activity_progress": (
					bucket["percent_sum"] / bucket["percent_count"] if bucket["percent_count"] else 0
				),
				"activity_overdue_count": bucket["activity_overdue_count"],
				"planned_start": bucket["planned_start"],
				"planned_finish": bucket["planned_finish"],
				"document_count": bucket["document_count"],
				"drawing_count": bucket["drawing_count"],
				"submittal_open_count": bucket["submittal_open_count"],
				"submittal_overdue_count": bucket["submittal_overdue_count"],
			}
		)
	return result


# --- reorder_wbs_nodes -----------------------------------------------------------------------


@frappe.whitelist()
def reorder_wbs_nodes(parent: str | None, ordered_names) -> None:
	# `ordered_names` arrives as a JSON-encoded string over a real HTTP call — Frappe v16's
	# whitelist argument-type validation (frappe.utils.typing_validations) validates against the
	# annotation with Pydantic's `validate_python`, not `validate_json`, so a `list[str]`
	# annotation here would reject the raw string before this function body ever runs (500,
	# `FrappeTypeError`). Deliberately untyped and parsed manually, matching the same pattern
	# `api/submittals.py`'s `create_workflow_template` already uses for its `steps` argument.
	if isinstance(ordered_names, str):
		ordered_names = frappe.parse_json(ordered_names)
	if not ordered_names:
		return

	rows = frappe.get_all(
		"EGC WBS Node",
		filters={"name": ("in", ordered_names)},
		fields=["name", "project", "parent_egc_wbs_node"],
	)
	by_name = {row.name: row for row in rows}

	missing = set(ordered_names) - set(by_name)
	if missing:
		frappe.throw(_("Unknown WBS Node(s): {0}").format(", ".join(sorted(missing))), exc=frappe.DoesNotExistError)

	stray = [name for name in ordered_names if by_name[name].parent_egc_wbs_node != (parent or None)]
	if stray:
		frappe.throw(
			_("{0} does not belong to the given parent.").format(frappe.bold(stray[0])),
			title=_("Invalid Reorder"),
			exc=frappe.ValidationError,
		)

	project = by_name[ordered_names[0]].project
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC WBS Node", "write", throw=True)

	for index, name in enumerate(ordered_names):
		frappe.db.set_value("EGC WBS Node", name, "sequence", index, update_modified=False)


# --- copy_wbs_branch --------------------------------------------------------------------------


def _unique_wbs_code(project: str, desired_code: str) -> str:
	code = desired_code
	suffix = 1
	while frappe.db.exists("EGC WBS Node", {"project": project, "wbs_code": code}):
		suffix += 1
		code = f"{desired_code}-COPY" if suffix == 2 else f"{desired_code}-COPY-{suffix}"
	return code


@frappe.whitelist()
def copy_wbs_branch(source_node: str, target_parent: str | None = None, project: str | None = None) -> str:
	source = frappe.get_doc("EGC WBS Node", source_node)
	target_project = project or source.project
	validators.require_project_permission(source.project, "read")
	validators.require_project_permission(target_project, "write")
	frappe.has_permission("EGC WBS Node", "create", throw=True)

	if target_parent:
		parent_project = frappe.db.get_value("EGC WBS Node", target_parent, "project")
		if parent_project != target_project:
			frappe.throw(
				_("Target parent belongs to project {0}, not {1}.").format(parent_project, target_project),
				exc=frappe.ValidationError,
			)

	def copy_node(node_name: str, new_parent: str | None) -> str:
		node = frappe.get_doc("EGC WBS Node", node_name)
		new_code = _unique_wbs_code(target_project, node.wbs_code)
		# `project` is always the TARGET, never inherited from `node` — the one place a cross-
		# project copy could leak the source's project into a child if this were forgotten
		# (validators.validate_same_project is what would catch it, but setting it right here
		# means that check never has anything to reject in the first place).
		new_node = frappe.get_doc(
			{
				"doctype": "EGC WBS Node",
				"project": target_project,
				"wbs_code": new_code,
				"wbs_name": node.wbs_name,
				"parent_egc_wbs_node": new_parent,
				"is_group": node.is_group,
				"discipline": node.discipline,
				"status": node.status,
				"sequence": node.sequence,
				"description": node.description,
			}
		)
		new_node.insert()

		for child in frappe.get_all("EGC WBS Node", filters={"parent_egc_wbs_node": node_name}, pluck="name"):
			copy_node(child, new_node.name)

		return new_node.name

	return copy_node(source_node, target_parent)


# --- bulk_create_wbs_nodes -------------------------------------------------------------------

_BULK_ROW_FIELDS = ("wbs_code", "wbs_name", "is_group", "discipline", "sequence")


@frappe.whitelist()
def bulk_create_wbs_nodes(parent: str | None, project: str, rows) -> list[str]:
	"""Creates every row as a sibling under `parent`. Aborts on the first invalid row and
	creates nothing — a partially-created bulk-add is a worse support problem than making the
	user fix one row and resubmit the whole batch.

	`rows` is deliberately untyped rather than `list[dict]` — see `reorder_wbs_nodes`'s
	`ordered_names` docstring for why a real HTTP call would 500 on that annotation."""
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC WBS Node", "create", throw=True)

	if isinstance(rows, str):
		rows = frappe.parse_json(rows)
	if not rows:
		return []

	created = []
	try:
		for index, row in enumerate(rows):
			doc = frappe.get_doc(
				{
					"doctype": "EGC WBS Node",
					"project": project,
					"parent_egc_wbs_node": parent,
					"wbs_code": row.get("wbs_code"),
					"wbs_name": row.get("wbs_name"),
					"is_group": row.get("is_group", 0),
					"discipline": row.get("discipline"),
					"sequence": row.get("sequence", index),
				}
			)
			doc.insert()
			created.append(doc.name)
	except Exception:
		for name in created:
			frappe.delete_doc("EGC WBS Node", name, force=True)
		raise

	return created
