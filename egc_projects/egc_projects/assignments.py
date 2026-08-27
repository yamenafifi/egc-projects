"""The many-to-many multi-person/multi-organization assignment layer (Level 0 §6/§40 of the
project-controls expansion: "Create a reusable project assignment architecture" — one clean
generic relationship model, not a new field or a new junction doctype per record type).

`EGC Assignment` is a standalone doctype, never a child table, for the same reason
`relationships.py`'s `EGC Activity Link` is: a Person can be assigned across many records and one
record can carry many assignees — a genuine many-to-many, and a real business relationship (a
person's Directory identity, their organization) that a numbered `responsible_user_2`-style field
or a comma-joined name string can never represent correctly.

`ALLOWED_ASSIGNMENT_DOCTYPES` is the single registry of what may carry assignments — starts with
`EGC Activity`; adding a future target (`EGC Submittal`, `EGC RFI`, ...) is a one-line change here,
mirroring `relationships.ALLOWED_LINK_DOCTYPES`'s own extensibility.
"""

from __future__ import annotations

import frappe
from frappe import _

#: doctype -> the fieldname on THAT doctype holding its own project. Every assignable doctype
#: must have a direct `project` field — this module never infers it transitively.
ALLOWED_ASSIGNMENT_DOCTYPES: dict[str, str] = {
	"EGC Activity": "project",
}

ASSIGNMENT_ROLES = (
	"Responsible",
	"Assignee",
	"Supervisor",
	"Consultant",
	"Reviewer",
	"Contractor",
	"Watcher",
)


def is_allowed(parent_doctype: str) -> bool:
	return parent_doctype in ALLOWED_ASSIGNMENT_DOCTYPES


def _person_label(person: str | None) -> str | None:
	if not person:
		return None
	return frappe.db.get_value("EGC Person", person, "full_name")


@frappe.whitelist()
def get_assignments_for(parent_doctype: str, parent_name: str) -> list[dict]:
	"""Every assignment on one record, each carrying its Person's live display fields so the
	caller never needs a second round-trip per row."""
	if not parent_doctype or not parent_name:
		return []
	frappe.has_permission(parent_doctype, "read", doc=parent_name, throw=True)

	rows = frappe.get_all(
		"EGC Assignment",
		filters={"parent_doctype": parent_doctype, "parent_name": parent_name},
		fields=[
			"name",
			"assignment_role",
			"is_primary",
			"person",
			"person_label",
			"organization",
			"remarks",
		],
		order_by="is_primary desc, creation asc",
	)
	if not rows:
		return []

	person_names = {row.person for row in rows if row.person}
	org_names = {row.organization for row in rows if row.organization}
	people = (
		{
			p.name: p
			for p in frappe.get_all(
				"EGC Person", filters={"name": ("in", list(person_names))}, fields=["name", "full_name", "title", "user"]
			)
		}
		if person_names
		else {}
	)
	orgs = (
		{
			o.name: o.organization_name
			for o in frappe.get_all(
				"EGC Organization", filters={"name": ("in", list(org_names))}, fields=["name", "organization_name"]
			)
		}
		if org_names
		else {}
	)

	result = []
	for row in rows:
		person = people.get(row.person)
		result.append(
			{
				"name": row.name,
				"assignment_role": row.assignment_role,
				"is_primary": row.is_primary,
				"person": row.person,
				"person_name": person.full_name if person else row.person_label,
				"person_title": person.title if person else None,
				"person_user": person.user if person else None,
				"organization": row.organization,
				"organization_name": orgs.get(row.organization),
				"remarks": row.remarks,
			}
		)
	return result


@frappe.whitelist()
def add_assignment(
	parent_doctype: str,
	parent_name: str,
	assignment_role: str,
	person: str | None = None,
	organization: str | None = None,
	remarks: str | None = None,
	is_primary: bool = False,
) -> str:
	if not is_allowed(parent_doctype):
		frappe.throw(
			_("{0} cannot carry assignments. Allowed: {1}").format(
				frappe.bold(parent_doctype or ""), ", ".join(ALLOWED_ASSIGNMENT_DOCTYPES.keys())
			),
			title=_("Not Allowed"),
			exc=frappe.ValidationError,
		)

	frappe.has_permission(parent_doctype, "write", doc=parent_name, throw=True)
	frappe.has_permission("EGC Assignment", "create", throw=True)

	doc = frappe.get_doc(
		{
			"doctype": "EGC Assignment",
			"parent_doctype": parent_doctype,
			"parent_name": parent_name,
			"assignment_role": assignment_role,
			"person": person,
			"organization": organization,
			"remarks": remarks,
			"is_primary": is_primary,
		}
	)
	doc.insert()
	return doc.name


@frappe.whitelist()
def remove_assignment(name: str) -> None:
	doc = frappe.get_doc("EGC Assignment", name)
	frappe.has_permission(doc.parent_doctype, "write", doc=doc.parent_name, throw=True)
	frappe.delete_doc("EGC Assignment", name)
