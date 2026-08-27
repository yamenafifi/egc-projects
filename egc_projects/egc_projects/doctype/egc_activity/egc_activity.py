"""EGC Activity — the execution breakdown.

A single self-referencing NestedSet DocType used recursively at every level (group activities,
leaf activities, milestones). There is no Sub-Activity DocType and ERPNext `Task` is not used
here — see docs/ARCHITECTURE.md §2.3.

**v2 addendum (docs/ARCHITECTURE_V2.md §5):** actual/forecast dates, `duration_days` and
`is_milestone` add schedule depth; a group Activity's `percent_complete`/dates/`duration_days`/
`status` are now derived from its children by `activity_control.py`, reversing v1's "groups are
manually entered, no roll-up" decision — see that module and §5's own callout for the reasoning.
Dependencies (`EGC Activity Dependency`, §6) are recorded and validated only — no automatic
forecast-date shifting or critical-path calculation, matching §6's explicit boundary.
"""

import frappe
from frappe import _
from frappe.desk.treeview import make_tree_args
from frappe.utils import date_diff, flt, getdate, sbool, today
from frappe.utils.nestedset import NestedSet

from egc_projects.egc_projects import activity_control, project_progress
from egc_projects.egc_projects.constants import (
	ACTIVITY_CLOSED_STATUSES,
	ACTIVITY_COMPLETED,
	ACTIVITY_NOT_STARTED,
)
from egc_projects.egc_projects.validators import (
	validate_project_not_changed_with_children,
	validate_same_project,
	validate_tree_parent,
	validate_unique_in_project,
)


def is_overdue(status: str | None, planned_end_date) -> bool:
	"""Derived overdue rule (docs/ARCHITECTURE.md §2.3) — never stored, always computed.

	`Completed` and `Cancelled` activities are never overdue, regardless of date, because the
	work is no longer being tracked against the plan.
	"""
	if not planned_end_date or status in ACTIVITY_CLOSED_STATUSES:
		return False
	return getdate(planned_end_date) < getdate(today())


class EGCActivity(NestedSet):
	# begin: auto-generated types
	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		actual_end_date: DF.Date | None
		actual_start_date: DF.Date | None
		activity_code: DF.Data
		activity_name: DF.Data
		description: DF.TextEditor | None
		discipline: DF.Link | None
		duration_days: DF.Int
		forecast_end_date: DF.Date | None
		forecast_start_date: DF.Date | None
		is_group: DF.Check
		is_milestone: DF.Check
		lft: DF.Int
		old_parent: DF.Data | None
		parent_egc_activity: DF.Link | None
		percent_complete: DF.Percent
		planned_end_date: DF.Date | None
		planned_start_date: DF.Date | None
		project: DF.Link
		rgt: DF.Int
		sequence: DF.Int
		status: DF.Literal["Not Started", "In Progress", "On Hold", "Completed", "Cancelled"]
		wbs_node: DF.Link | None
		weight_pct: DF.Percent
	# end: auto-generated types

	nsm_parent_field = "parent_egc_activity"

	def validate(self):
		validate_tree_parent(self, "parent_egc_activity", "Activity")
		validate_unique_in_project(self, "activity_code", "Activity Code")
		validate_project_not_changed_with_children(self, "parent_egc_activity", "Activity")
		validate_same_project(self, "wbs_node", "EGC WBS Node", "WBS Node")
		self.validate_dates()
		self.compute_duration()
		self.validate_progress()
		self.validate_weight()
		activity_control.assert_group_fields_not_hand_edited(self)

	def validate_dates(self):
		if self.planned_start_date and self.planned_end_date:
			if getdate(self.planned_end_date) < getdate(self.planned_start_date):
				frappe.throw(
					_("Planned End Date cannot be before Planned Start Date."),
					frappe.exceptions.InvalidDates,
				)

	def compute_duration(self):
		# A group's duration_days is rollup-owned (activity_control.py, from the rolled-up
		# planned dates) — recomputing it here from the group's own fields would fight the
		# engine's write on every save, so only a leaf computes its own duration.
		if self.is_group:
			return
		if self.planned_start_date and self.planned_end_date:
			self.duration_days = date_diff(self.planned_end_date, self.planned_start_date) + 1
		else:
			# `duration_days` is an Int field — Frappe would coerce a bare `None` to 0 here too
			# (`cint(None) == 0` in `get_valid_dict`), but writing 0 explicitly keeps this in
			# sync with activity_control.py's own rollup writes, which go through
			# `frappe.db.set_value` and get no such coercion. See that module for why 0 is an
			# unambiguous "not computed" (the formula above can never itself produce 0).
			self.duration_days = 0

	def validate_progress(self):
		# The two terminal statuses own percent_complete outright; any other status (including
		# a manually-entered 100% while still "In Progress") is left for the user to resolve.
		if self.status == ACTIVITY_COMPLETED:
			self.percent_complete = 100
		elif self.status == ACTIVITY_NOT_STARTED:
			self.percent_complete = 0
		else:
			self.percent_complete = max(0, min(100, flt(self.percent_complete)))

	def validate_weight(self):
		"""Every set of siblings (same `parent_egc_activity`, including root-level Activities of
		the same project, where the "parent" is blank) may total at most 100% — manually entered
		for now, per the brief; automatic allocation is a documented future improvement, not
		implemented here. Clamped to [0, 100] first so a single row can never itself be invalid;
		the sibling-sum check is what actually enforces the 100% ceiling. Under-allocation (a
		tree still being built out) is deliberately allowed — only exceeding 100% is rejected.
		"""
		self.weight_pct = max(0, min(100, flt(self.weight_pct)))

		siblings_total = frappe.db.sql(
			"""select coalesce(sum(weight_pct), 0) from `tabEGC Activity`
			where project = %(project)s
				and ifnull(parent_egc_activity, '') = %(parent)s
				and name != %(name)s""",
			{
				"project": self.project,
				"parent": self.parent_egc_activity or "",
				# `self.name` is unset on a brand-new doc until after insert; comparing against
				# a value nothing can ever match is equivalent to "no exclusion" in that case.
				"name": self.name or "",
			},
		)[0][0]

		total = flt(siblings_total) + flt(self.weight_pct)
		if total > 100 + 1e-6:
			frappe.throw(
				_(
					"Weight allocation among these siblings (same Parent Activity) would total"
					" {0}%, exceeding 100%. Reduce this Activity's weight or another sibling's."
				).format(frappe.format(total, {"fieldtype": "Float", "precision": 2})),
				title=_("Over-Allocated"),
				exc=frappe.ValidationError,
			)

	def on_update(self):
		super().on_update()
		activity_control.refresh_ancestors(self.parent_egc_activity)
		project_progress.refresh_project_percent_complete(self.project)

	def on_trash(self, allow_root_deletion=False):
		# NestedSet.on_trash() clears self.parent_egc_activity on the in-memory doc before
		# returning (it detaches the node from the tree ahead of the row's own deletion), so the
		# parent to refresh must be captured before calling it, not after.
		parent = self.parent_egc_activity
		project = self.project
		super().on_trash(allow_root_deletion=allow_root_deletion)
		activity_control.refresh_ancestors(parent)
		project_progress.refresh_project_percent_complete(project)

	@property
	def is_overdue(self) -> bool:
		return is_overdue(self.status, self.planned_end_date)


@frappe.whitelist()
def get_children(doctype, parent=None, project=None, wbs_node=None, is_root=False, **kwargs):
	"""Tree data source for `egc_activity_tree.js`. Enforces the project filter server-side."""
	if not project:
		frappe.throw(_("Project is required."))
	if not frappe.db.exists("Project", project):
		frappe.throw(_("Project {0} not found.").format(project))
	frappe.has_permission("Project", "read", doc=project, throw=True)

	filters = {"project": project}
	drilling_down = not sbool(is_root) and parent and parent not in ("All Activities", project)

	if drilling_down:
		# Once the user has drilled into a node, show its real children. Re-applying the WBS
		# filter here would hide children that hang off a matching activity but carry a
		# different (or no) WBS node of their own.
		filters["parent_egc_activity"] = parent
	elif wbs_node:
		# At root level the WBS filter means "activities assigned to this WBS node", wherever
		# they sit in the activity tree. Keeping the parent filter as well would return
		# nothing whenever the matching activities are not themselves roots.
		filters["wbs_node"] = wbs_node
	else:
		filters["parent_egc_activity"] = ("in", ("", None))

	activities = frappe.get_list(
		"EGC Activity",
		fields=[
			"name as value",
			"activity_code",
			"activity_name",
			"status",
			"is_group as expandable",
		],
		filters=filters,
		order_by="sequence asc, activity_code asc",
	)
	for activity in activities:
		activity["title"] = f"{activity.get('activity_code')}: {activity.get('activity_name')}"
	return activities


@frappe.whitelist()
def add_node():
	"""Whitelisted create endpoint for the tree's "New" dialog. Forces `project` from the parent."""
	args = frappe.form_dict
	args = make_tree_args(**args)

	project = args.get("project")
	if not project:
		frappe.throw(_("Project is required."))
	frappe.has_permission("Project", "write", doc=project, throw=True)

	parent = args.get("parent_egc_activity")
	if sbool(args.get("is_root")) or not parent or parent in ("All Activities", project):
		args["parent_egc_activity"] = None
	elif frappe.db.get_value("EGC Activity", parent, "project") != project:
		frappe.throw(_("Parent Activity {0} belongs to a different project.").format(parent))

	frappe.get_doc(args).insert()
