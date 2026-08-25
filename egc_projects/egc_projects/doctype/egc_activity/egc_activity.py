"""EGC Activity — the execution breakdown.

A single self-referencing NestedSet DocType used recursively at every level (group activities,
leaf activities, milestones). There is no Sub-Activity DocType and ERPNext `Task` is not used
here — see docs/ARCHITECTURE.md §2.3. Dependencies, lag, baselines, calendars, critical path and
progress roll-up are deferred (§9) and must not be added here.
"""

import frappe
from frappe import _
from frappe.desk.treeview import make_tree_args
from frappe.utils import flt, getdate, sbool, today
from frappe.utils.nestedset import NestedSet

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

		activity_code: DF.Data
		activity_name: DF.Data
		description: DF.TextEditor | None
		discipline: DF.Link | None
		is_group: DF.Check
		lft: DF.Int
		old_parent: DF.Data | None
		parent_egc_activity: DF.Link | None
		percent_complete: DF.Percent
		planned_end_date: DF.Date | None
		planned_start_date: DF.Date | None
		project: DF.Link
		responsible_user: DF.Link | None
		rgt: DF.Int
		sequence: DF.Int
		status: DF.Literal["Not Started", "In Progress", "On Hold", "Completed", "Cancelled"]
		wbs_node: DF.Link | None
	# end: auto-generated types

	nsm_parent_field = "parent_egc_activity"

	def validate(self):
		validate_tree_parent(self, "parent_egc_activity", "Activity")
		validate_unique_in_project(self, "activity_code", "Activity Code")
		validate_project_not_changed_with_children(self, "parent_egc_activity", "Activity")
		validate_same_project(self, "wbs_node", "EGC WBS Node", "WBS Node")
		self.validate_dates()
		self.validate_progress()

	def validate_dates(self):
		if self.planned_start_date and self.planned_end_date:
			if getdate(self.planned_end_date) < getdate(self.planned_start_date):
				frappe.throw(
					_("Planned End Date cannot be before Planned Start Date."),
					frappe.exceptions.InvalidDates,
				)

	def validate_progress(self):
		# The two terminal statuses own percent_complete outright; any other status (including
		# a manually-entered 100% while still "In Progress") is left for the user to resolve.
		if self.status == ACTIVITY_COMPLETED:
			self.percent_complete = 100
		elif self.status == ACTIVITY_NOT_STARTED:
			self.percent_complete = 0
		else:
			self.percent_complete = max(0, min(100, flt(self.percent_complete)))

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
