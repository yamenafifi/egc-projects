# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from frappe.utils.nestedset import NestedSet

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects.validators import (
	require_project_permission,
	validate_project_not_changed_with_children,
	validate_tree_parent,
	validate_unique_in_project,
)


class EGCWBSNode(NestedSet):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		description: DF.SmallText | None
		discipline: DF.Link | None
		is_group: DF.Check
		lft: DF.Int
		old_parent: DF.Data | None
		parent_egc_wbs_node: DF.Link | None
		project: DF.Link
		rgt: DF.Int
		sequence: DF.Int
		status: DF.Literal["Active", "On Hold", "Completed", "Cancelled"]
		wbs_code: DF.Data
		wbs_name: DF.Data
	# end: auto-generated types

	nsm_parent_field = "parent_egc_wbs_node"

	def validate(self) -> None:
		validate_tree_parent(self, "parent_egc_wbs_node", "WBS Node")
		validate_unique_in_project(self, "wbs_code", "WBS Code")
		validate_project_not_changed_with_children(self, "parent_egc_wbs_node", "WBS Node")
		self.validate_completion_requires_activities_done()

	def validate_completion_requires_activities_done(self) -> None:
		"""A WBS node can only be marked Completed once every Activity tagged anywhere in its
		WHOLE SUBTREE is itself at 100% — direct user instruction. Subtree-wide, not
		direct-children-only, for the exact reason `api/wbs.py`'s `get_wbs_summary` docstring
		already gives: a group node like "Mechanical" typically has nothing tagged directly
		against it at all (its Activities sit on a descendant like "HVAC" instead), so a
		direct-only check would trivially pass with zero activities checked — the opposite of
		this rule's intent. Cancelled activities are excluded from the check, mirroring
		`activity_control._rollup_status`'s own exclusion: an abandoned line of work must not be
		the one thing blocking a phase from closing out.

		Skipped for a brand-new node (`is_new()`): nothing could already reference a node that
		doesn't exist yet, so there is trivially nothing to check.
		"""
		if self.status != c.WBS_COMPLETED or self.is_new():
			return

		subtree_nodes = frappe.get_all(
			"EGC WBS Node",
			filters={"project": self.project, "lft": (">=", self.lft), "rgt": ("<=", self.rgt)},
			pluck="name",
		)
		incomplete = frappe.get_all(
			"EGC Activity",
			filters={
				"wbs_node": ("in", subtree_nodes),
				"status": ("!=", c.ACTIVITY_CANCELLED),
				"percent_complete": ("<", 100),
			},
			fields=["activity_code", "activity_name", "percent_complete"],
			order_by="activity_code asc",
			limit=1,
		)
		if incomplete:
			activity = incomplete[0]
			frappe.throw(
				_(
					"{0} cannot be marked Completed — {1}: {2} is only {3}% complete. Every"
					" Activity under this WBS node must reach 100% first."
				).format(
					frappe.bold(self.wbs_code),
					activity.activity_code,
					activity.activity_name,
					round(flt(activity.percent_complete)),
				),
				title=_("Not Allowed"),
				exc=frappe.ValidationError,
			)

	# NestedSet.on_update() rebuilds lft/rgt via update_nsm() and does NOT call
	# validate_one_root() itself — that call is opt-in per doctype (see ItemGroup.on_update).
	# We deliberately do not add it: multiple roots, one per project, are required here.


@frappe.whitelist()
def get_children(
	doctype: str,
	parent: str | None = None,
	project: str | None = None,
	is_root: bool | str = False,
	**filters,
) -> list[dict]:
	"""Tree-view data source for `EGC WBS Node`, modelled on
	`erpnext.projects.doctype.task.task.get_children`.

	The tree has no single root record — each project owns its own root nodes — so the
	client always drives it with a mandatory Project filter (`egc_wbs_node_tree.js`,
	`get_tree_root: false`). `require_project_permission` is both the source of the "project
	is required" rule and the permission check: server-side enforcement, not merely the
	client-side filter (docs/ARCHITECTURE.md §0.5).
	"""
	is_root = frappe.utils.sbool(is_root)
	require_project_permission(project, "read")

	node_filters: dict = {"project": project}
	if parent and not is_root:
		node_filters["parent_egc_wbs_node"] = parent
	else:
		node_filters["parent_egc_wbs_node"] = ("in", ("", None))

	return frappe.get_list(
		"EGC WBS Node",
		fields=["name as value", "wbs_name as title", "is_group as expandable"],
		filters=node_filters,
		order_by="sequence, wbs_code",
	)


@frappe.whitelist()
def add_node() -> None:
	"""Create-from-tree endpoint, modelled on
	`erpnext.projects.doctype.task.task.add_node`.

	`make_tree_args` treats whatever the tree passed as `parent` as the new node's parent —
	but at root level that "parent" is the pseudo-root value the treeview substitutes for a
	missing root record, i.e. the Project itself (see `frappe/public/js/frappe/views/
	treeview.js` `make_tree()`), not an `EGC WBS Node`. We must not let that leak into
	`parent_egc_wbs_node`. `project` is always taken from the real parent node when there is
	one, so a caller cannot smuggle a node into a different project than its parent.
	"""
	from frappe.desk.treeview import make_tree_args

	args = make_tree_args(**frappe.form_dict)

	project = args.get("project")
	if not project:
		frappe.throw(_("Project is required."))

	parent = args.get("parent_egc_wbs_node")
	if args.get("is_root") or parent == project:
		args["parent_egc_wbs_node"] = None
	elif parent:
		parent_project = frappe.db.get_value("EGC WBS Node", parent, "project")
		if parent_project:
			project = parent_project

	args["project"] = project
	frappe.get_doc(args).insert()
