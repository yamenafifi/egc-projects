"""Shared server-side validators.

Project isolation is a hard integrity rule (see docs/ARCHITECTURE.md §0.5): a record from
Project A must never be linked into Project B. Client-side `get_query` filters are UX only —
every rule below must be enforced here, on the server, for every write path including the
REST API and `frappe.client.set_value`.
"""

import frappe
from frappe import _


def get_project_of(doctype: str, name: str) -> str | None:
	"""Return the `project` of any EGC record without loading the whole document."""
	if not name:
		return None
	return frappe.db.get_value(doctype, name, "project")


def validate_same_project(doc, fieldname: str, link_doctype: str, label: str | None = None) -> None:
	"""Assert that the record linked in `doc.<fieldname>` belongs to `doc.project`."""
	value = doc.get(fieldname)
	if not value:
		return

	linked_project = get_project_of(link_doctype, value)
	if linked_project and linked_project != doc.project:
		frappe.throw(
			_("{0} {1} belongs to project {2}, not {3}.").format(
				_(label or link_doctype),
				frappe.bold(value),
				frappe.bold(linked_project),
				frappe.bold(doc.project or ""),
			),
			title=_("Cross-Project Link Rejected"),
		)


def validate_unique_in_project(doc, fieldname: str, label: str) -> None:
	"""Assert `doc.<fieldname>` is unique among documents of the same doctype and project.

	Uniqueness is scoped to the project deliberately: document and drawing numbers follow
	external document-control conventions and legitimately repeat between projects.
	"""
	value = (doc.get(fieldname) or "").strip()
	if not value or not doc.project:
		return

	doc.set(fieldname, value)

	existing = frappe.db.get_value(
		doc.doctype,
		{
			"project": doc.project,
			fieldname: value,
			"name": ("!=", doc.name or ""),
		},
		"name",
	)
	if existing:
		frappe.throw(
			_("{0} {1} already exists in project {2} ({3}).").format(
				_(label), frappe.bold(value), frappe.bold(doc.project), existing
			),
			title=_("Duplicate"),
			exc=frappe.DuplicateEntryError,
		)


def validate_unique_under_parent(doc, parent_field: str, fieldname: str, label: str) -> None:
	"""Assert `doc.<fieldname>` is unique among siblings sharing `doc.<parent_field>`.

	Used for revision labels, which are unique within their document / submittal only.
	"""
	value = (doc.get(fieldname) or "").strip()
	parent = doc.get(parent_field)
	if not value or not parent:
		return

	doc.set(fieldname, value)

	existing = frappe.db.get_value(
		doc.doctype,
		{
			parent_field: parent,
			fieldname: value,
			"name": ("!=", doc.name or ""),
			"docstatus": ("<", 2),
		},
		"name",
	)
	if existing:
		frappe.throw(
			_("{0} {1} already exists for {2} ({3}).").format(
				_(label), frappe.bold(value), frappe.bold(parent), existing
			),
			title=_("Duplicate Revision"),
			exc=frappe.DuplicateEntryError,
		)


def validate_tree_parent(doc, parent_field: str, label: str) -> None:
	"""Validate a NestedSet parent link: same project, is a group, and not self.

	Applies to both `EGC WBS Node` and `EGC Activity`, which share tree semantics but are
	deliberately independent hierarchies.
	"""
	parent = doc.get(parent_field)
	if not parent:
		return

	if parent == doc.name:
		frappe.throw(_("{0} cannot be its own parent.").format(_(label)))

	parent_row = frappe.db.get_value(doc.doctype, parent, ["project", "is_group"], as_dict=True)
	if not parent_row:
		frappe.throw(_("Parent {0} {1} does not exist.").format(_(label), frappe.bold(parent)))

	if parent_row.project != doc.project:
		frappe.throw(
			_("Parent {0} {1} belongs to project {2}, not {3}.").format(
				_(label),
				frappe.bold(parent),
				frappe.bold(parent_row.project),
				frappe.bold(doc.project or ""),
			),
			title=_("Cross-Project Link Rejected"),
		)

	if not parent_row.is_group:
		frappe.throw(
			_("Parent {0} {1} must be a group.").format(_(label), frappe.bold(parent)),
			title=_("Invalid Parent"),
		)


def validate_project_not_changed_with_children(doc, parent_field: str, label: str) -> None:
	"""Block moving a tree node to another project while it still has descendants.

	Re-parenting the whole subtree is not something we want to do implicitly; the user must
	detach children first, so no descendant is silently orphaned into the wrong project.
	"""
	if doc.is_new():
		return

	previous = doc.get_doc_before_save()
	if not previous or previous.project == doc.project:
		return

	if frappe.db.exists(doc.doctype, {parent_field: doc.name}):
		frappe.throw(
			_("Cannot move {0} {1} to another project while it has children.").format(
				_(label), frappe.bold(doc.name)
			)
		)


def require_project_permission(project: str, ptype: str = "read") -> None:
	"""Gate for whitelisted API methods. Every Hub endpoint must call this first."""
	if not project:
		frappe.throw(_("Project is required."), exc=frappe.ValidationError)

	if not frappe.db.exists("Project", project):
		frappe.throw(_("Project {0} not found.").format(project), exc=frappe.DoesNotExistError)

	frappe.has_permission("Project", ptype, doc=project, throw=True)
