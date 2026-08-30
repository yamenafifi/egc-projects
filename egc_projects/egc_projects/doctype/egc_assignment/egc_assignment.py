# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""`EGC Assignment` — the generic multi-person/multi-organization relationship row. See
`assignments.py` for the module docstring explaining why this exists as one polymorphic doctype
rather than a per-record-type junction table.

No composite unique DB index is declared in the JSON (Frappe v16's DocType schema has no key for
a multi-column unique constraint), so the (`parent_doctype`, `parent_name`, `person`,
`assignment_role`) uniqueness rule is enforced here in `validate()`, matching
`EGC Activity Link`'s own documented reasoning for the same gap.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from egc_projects.egc_projects import directory
from egc_projects.egc_projects.assignments import ALLOWED_ASSIGNMENT_DOCTYPES, is_allowed


class EGCAssignment(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		assignment_role: DF.Literal["Responsible", "Assignee", "Supervisor", "Consultant", "Reviewer", "Contractor", "Watcher"]
		is_primary: DF.Check
		organization: DF.DynamicLink | None
		organization_type: DF.Literal["", "Customer", "Supplier"]
		parent_doctype: DF.Link
		parent_name: DF.DynamicLink
		person: DF.Link | None
		person_label: DF.Data | None
		project: DF.Link
		remarks: DF.SmallText | None
	# end: auto-generated types

	def validate(self):
		self.validate_parent_doctype_allowed()
		self.validate_person_or_organization_set()
		self.set_project_from_parent()
		self.fetch_organization_from_person()
		self.set_person_label()
		self.validate_duplicate()

	def validate_parent_doctype_allowed(self):
		if not is_allowed(self.parent_doctype):
			frappe.throw(
				_("{0} cannot carry assignments. Allowed: {1}").format(
					frappe.bold(self.parent_doctype or ""), ", ".join(ALLOWED_ASSIGNMENT_DOCTYPES.keys())
				),
				title=_("Not Allowed"),
				exc=frappe.ValidationError,
			)

	def validate_person_or_organization_set(self):
		if not self.person and not self.organization:
			frappe.throw(
				_("Set a Person, an Organization, or both — an assignment needs at least one."),
				title=_("Nothing to Assign"),
				exc=frappe.ValidationError,
			)

	def set_project_from_parent(self):
		# Never trust a client-supplied `project` — always derived from the parent record, the
		# same discipline `EGC Activity Link.set_project_from_activity` already uses.
		project_field = ALLOWED_ASSIGNMENT_DOCTYPES[self.parent_doctype]
		project = frappe.db.get_value(self.parent_doctype, self.parent_name, project_field)
		if not project:
			frappe.throw(_("{0} {1} not found.").format(_(self.parent_doctype), frappe.bold(self.parent_name)))
		self.project = project

	def fetch_organization_from_person(self):
		if self.person and not self.organization:
			org = directory.resolve_organization(self.person)
			if org:
				self.organization_type, self.organization = org

	def set_person_label(self):
		self.person_label = frappe.db.get_value("User", self.person, "full_name") if self.person else None

	def validate_duplicate(self):
		if not self.person:
			return
		existing = frappe.db.get_value(
			"EGC Assignment",
			{
				"parent_doctype": self.parent_doctype,
				"parent_name": self.parent_name,
				"person": self.person,
				"assignment_role": self.assignment_role,
				"name": ("!=", self.name or ""),
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("{0} is already assigned as {1} on {2} ({3}).").format(
					frappe.bold(self.person_label or self.person),
					_(self.assignment_role),
					frappe.bold(self.parent_name),
					existing,
				),
				title=_("Duplicate Assignment"),
				exc=frappe.DuplicateEntryError,
			)
