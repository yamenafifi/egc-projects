"""Whitelisted API behind the Hub's Activities/Schedule tab and Gantt view
(docs/ARCHITECTURE_V2.md §5, §6, §12).

Follows `api/documents.py`'s conventions verbatim: `validators.require_project_permission` first
on every read, a second `frappe.has_permission` gate on the specific EGC doctype for every write,
`frappe.get_all` only, no raw SQL. This module owns no business state — `percent_complete`,
schedule dates and `status` on a group Activity are `activity_control.py`'s; this module only
ever reads them or, for a leaf, writes them through the DocType's own `validate()`/`on_update`
(never by shortcutting the rollup engine).

Dependencies are recorded and validated by `EGC Activity Dependency` itself; nothing here shifts
a forecast date or computes a critical path — that stays out of scope per §6's explicit boundary.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import relationships, validators
from egc_projects.egc_projects.doctype.egc_activity.egc_activity import is_overdue

# --- shared field lists --------------------------------------------------------------------------

_ACTIVITY_DETAIL_FIELDS = (
	"name",
	"project",
	"activity_code",
	"activity_name",
	"parent_egc_activity",
	"is_group",
	"sequence",
	"wbs_node",
	"discipline",
	"planned_start_date",
	"planned_end_date",
	"duration_days",
	"is_milestone",
	"actual_start_date",
	"actual_end_date",
	"forecast_start_date",
	"forecast_end_date",
	"status",
	"percent_complete",
	"responsible_user",
	"responsible_supplier",
	"description",
)

_CHILD_ROW_FIELDS = (
	"name",
	"activity_code",
	"activity_name",
	"is_group",
	"status",
	"percent_complete",
	"planned_start_date",
	"planned_end_date",
	"is_milestone",
)

_DEPENDENCY_EDGE_FIELDS = ("name", "dependency_type", "lag_days")


def _activity_dict(activity: str) -> dict:
	return frappe.db.get_value("EGC Activity", activity, _ACTIVITY_DETAIL_FIELDS, as_dict=True)


def _children_rows(activity: str) -> list[dict]:
	return frappe.get_all(
		"EGC Activity",
		filters={"parent_egc_activity": activity},
		fields=list(_CHILD_ROW_FIELDS),
		order_by="sequence asc, activity_code asc",
	)


def _shape_dependency_edge(edge: dict, other_id: str | None, activities: dict[str, dict]) -> dict:
	other = activities.get(other_id) if other_id else None
	return {
		"name": edge["name"],
		"activity": other_id,
		"activity_code": other.activity_code if other else None,
		"activity_name": other.activity_name if other else None,
		"status": other.status if other else None,
		"dependency_type": edge["dependency_type"],
		"lag_days": edge["lag_days"],
	}


def _dependency_rows(activity: str) -> dict:
	"""Both directions of `activity`'s dependencies, each carrying the OTHER activity's display
	fields so the caller never needs a second round-trip per row."""
	predecessor_edges = frappe.get_all(
		"EGC Activity Dependency",
		filters={"successor": activity},
		fields=["predecessor", *_DEPENDENCY_EDGE_FIELDS],
		order_by="creation asc",
	)
	successor_edges = frappe.get_all(
		"EGC Activity Dependency",
		filters={"predecessor": activity},
		fields=["successor", *_DEPENDENCY_EDGE_FIELDS],
		order_by="creation asc",
	)

	other_names = {row.predecessor for row in predecessor_edges} | {row.successor for row in successor_edges}
	activities = (
		{
			row.name: row
			for row in frappe.get_all(
				"EGC Activity",
				filters={"name": ("in", list(other_names))},
				fields=["name", "activity_code", "activity_name", "status"],
			)
		}
		if other_names
		else {}
	)

	return {
		"predecessors": [
			_shape_dependency_edge(edge, edge.predecessor, activities) for edge in predecessor_edges
		],
		"successors": [
			_shape_dependency_edge(edge, edge.successor, activities) for edge in successor_edges
		],
	}


@frappe.whitelist()
def get_activity_detail(activity: str) -> dict:
	if not activity or not frappe.db.exists("EGC Activity", activity):
		frappe.throw(_("Activity {0} not found.").format(activity), exc=frappe.DoesNotExistError)

	project = validators.get_project_of("EGC Activity", activity)
	validators.require_project_permission(project)

	return {
		"activity": _activity_dict(activity),
		"children": _children_rows(activity),
		"dependencies": _dependency_rows(activity),
		# Reuses relationships.py's existing registry-driven join rather than reimplementing it
		# here — this is the same "Linked Documents & Submittals" data the native form already
		# shows, batched one query per distinct target doctype.
		"links": relationships.get_links_for_activity(activity),
	}


# --- get_activity_gantt_rows ----------------------------------------------------------------------


def _predecessor_map(project: str) -> dict[str, list[str]]:
	edges = frappe.get_all(
		"EGC Activity Dependency",
		filters={"project": project},
		fields=["predecessor", "successor"],
	)
	result: dict[str, list[str]] = {}
	for edge in edges:
		result.setdefault(edge.successor, []).append(edge.predecessor)
	return result


def _gantt_custom_class(row) -> str | None:
	classes = []
	if row.is_milestone:
		classes.append("egc-gantt-milestone")
	if is_overdue(row.status, row.planned_end_date):
		classes.append("egc-gantt-overdue")
	return " ".join(classes) if classes else None


@frappe.whitelist()
def get_activity_gantt_rows(project: str) -> list[dict]:
	"""Every Activity of `project`, shaped for `frappe-gantt` (`apps/frappe/node_modules/
	frappe-gantt`; see also `frappe/public/js/frappe/views/gantt/gantt_view.js`'s own `id`/`name`/
	`start`/`end`/`progress`/`dependencies`/`custom_class` task shape, which this mirrors).
	`dependencies` is a comma-separated string of predecessor ids — the exact format
	`frappe-gantt` parses (`Gantt.setup_tasks`: `task.dependencies.split(',')`).
	"""
	validators.require_project_permission(project)

	activities = frappe.get_all(
		"EGC Activity",
		filters={"project": project},
		fields=[
			"name",
			"activity_code",
			"activity_name",
			"status",
			"percent_complete",
			"planned_start_date",
			"planned_end_date",
			"is_milestone",
			"is_group",
		],
		order_by="sequence asc, activity_code asc",
	)
	if not activities:
		return []

	predecessor_map = _predecessor_map(project)

	return [
		{
			"id": row.name,
			"name": f"{row.activity_code}: {row.activity_name}",
			"start": row.planned_start_date,
			"end": row.planned_end_date,
			"progress": flt(row.percent_complete),
			"dependencies": ",".join(predecessor_map.get(row.name, [])),
			"custom_class": _gantt_custom_class(row),
		}
		for row in activities
	]


# --- add_dependency / remove_dependency -----------------------------------------------------------


@frappe.whitelist()
def add_dependency(
	predecessor: str,
	successor: str,
	dependency_type: str = c.DEPENDENCY_FS,
	lag_days: int = 0,
) -> str:
	"""Thin wrapper over `frappe.get_doc(...).insert()` — every rule (same project, no self-
	dependency, no duplicate pair, no cycle) is `EGC Activity Dependency.validate()`'s own; this
	function adds nothing beyond the two permission gates."""
	if not predecessor or not frappe.db.exists("EGC Activity", predecessor):
		frappe.throw(_("Activity {0} not found.").format(predecessor), exc=frappe.DoesNotExistError)

	project = validators.get_project_of("EGC Activity", predecessor)
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC Activity Dependency", "create", throw=True)

	doc = frappe.get_doc(
		{
			"doctype": "EGC Activity Dependency",
			"predecessor": predecessor,
			"successor": successor,
			"dependency_type": dependency_type or c.DEPENDENCY_FS,
			"lag_days": lag_days or 0,
		}
	)
	doc.insert()
	return doc.name


@frappe.whitelist()
def remove_dependency(name: str) -> None:
	if not name or not frappe.db.exists("EGC Activity Dependency", name):
		frappe.throw(_("Dependency {0} not found.").format(name), exc=frappe.DoesNotExistError)

	project = frappe.db.get_value("EGC Activity Dependency", name, "project")
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC Activity Dependency", "delete", throw=True)

	frappe.delete_doc("EGC Activity Dependency", name)


# --- update_activity_progress -----------------------------------------------------------------------


@frappe.whitelist()
def update_activity_progress(activity: str, percent_complete, status: str | None = None) -> dict:
	"""The Activity detail workspace's inline "update progress" quick action
	(docs/ARCHITECTURE_V2.md §8's mockup). Rejects a group Activity outright — its progress is
	rollup-owned by `activity_control.py`, exactly like the DocType's own `read_only_depends_on`
	rule, so there is no direct-edit path into it even from this endpoint.

	Goes through the normal `doc.save()` path (not `db_set`) deliberately: a leaf's own
	`on_update` is what calls `activity_control.refresh_ancestors`, so a progress update here
	propagates up the whole ancestor chain exactly as a native form save would.
	"""
	if not activity or not frappe.db.exists("EGC Activity", activity):
		frappe.throw(_("Activity {0} not found.").format(activity), exc=frappe.DoesNotExistError)

	project = validators.get_project_of("EGC Activity", activity)
	validators.require_project_permission(project, "write")
	frappe.has_permission("EGC Activity", "write", doc=activity, throw=True)

	doc = frappe.get_doc("EGC Activity", activity)
	if doc.is_group:
		frappe.throw(
			_(
				"{0} is a group Activity; its progress is derived from its children and cannot"
				" be set directly."
			).format(frappe.bold(activity)),
			title=_("Not Allowed"),
			exc=frappe.ValidationError,
		)

	doc.percent_complete = percent_complete
	if status:
		doc.status = status
	doc.save()
	return _activity_dict(activity)
