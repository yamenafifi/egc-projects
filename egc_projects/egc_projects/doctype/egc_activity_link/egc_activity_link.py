# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""`EGC Activity Link` — the many-to-many relationship row (see docs/ARCHITECTURE.md §2.6).

`is_blocking`, `required_status` and `stage` are reserved for a future readiness engine, which
is explicitly deferred (§9). Nothing in this controller — or anywhere else in v1 — reads them;
they exist only so that engine won't need a schema change later.

No composite unique DB index is declared in the JSON: Frappe v16's DocType schema has no key for
a multi-column unique constraint (only single-field `"unique": 1`), so the (`activity`,
`link_doctype`, `link_name`) uniqueness rule is enforced here in `validate()` only, as the
architecture allows when a clean JSON declaration isn't available.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from egc_projects.egc_projects.relationships import ALLOWED_LINK_DOCTYPES, is_allowed
from egc_projects.egc_projects.validators import validate_same_project


class EGCActivityLink(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		activity: DF.Link
		is_blocking: DF.Check
		link_doctype: DF.Link
		link_name: DF.DynamicLink
		link_purpose: DF.Literal["Reference", "Requirement"]
		link_title: DF.Data | None
		project: DF.Link
		remarks: DF.SmallText | None
		required_status: DF.Data | None
		stage: DF.Data | None
	# end: auto-generated types

	def validate(self):
		self.validate_link_doctype_allowed()
		self.set_project_from_activity()
		self.validate_activity_not_group()
		self.validate_target_same_project()
		self.set_link_title()
		self.validate_duplicate()

	def validate_activity_not_group(self):
		"""Level 0 §9-§22: a Group Activity is a phase/summary node, not a place work actually
		happens — Submittals, Documents and (future) RFIs/Inspections belong on the leaf Activity
		that represents the real scope, never on the group that just rolls its children up."""
		if frappe.db.get_value("EGC Activity", self.activity, "is_group"):
			label = ALLOWED_LINK_DOCTYPES.get(self.link_doctype, {}).get("label", self.link_doctype)
			frappe.throw(
				_(
					"{0} is a Group Activity. {1} records belong on the leaf Activity that"
					" represents the actual work, not on the group that summarises it."
				).format(frappe.bold(self.activity), label),
				title=_("Not Allowed on a Group Activity"),
				exc=frappe.ValidationError,
			)

	def validate_link_doctype_allowed(self):
		# The client `get_query` on `link_doctype` is UX only; this is the enforcement (§0.5).
		if not is_allowed(self.link_doctype):
			frappe.throw(
				_("{0} is not a linkable record type. Allowed: {1}").format(
					frappe.bold(self.link_doctype or ""), ", ".join(ALLOWED_LINK_DOCTYPES.keys())
				),
				title=_("Not Allowed"),
				exc=frappe.ValidationError,
			)

	def set_project_from_activity(self):
		# Never trust a client-supplied `project` — it is always derived from the activity.
		project = frappe.db.get_value("EGC Activity", self.activity, "project")
		if not project:
			frappe.throw(_("Activity {0} not found.").format(frappe.bold(self.activity)))
		self.project = project

	def validate_target_same_project(self):
		label = ALLOWED_LINK_DOCTYPES.get(self.link_doctype, {}).get("label", self.link_doctype)
		validate_same_project(self, "link_name", self.link_doctype, label)

	def set_link_title(self):
		title_field = ALLOWED_LINK_DOCTYPES.get(self.link_doctype, {}).get("title_field")
		self.link_title = (
			frappe.db.get_value(self.link_doctype, self.link_name, title_field)
			if title_field
			else self.link_name
		)

	def validate_duplicate(self):
		existing = frappe.db.get_value(
			"EGC Activity Link",
			{
				"activity": self.activity,
				"link_doctype": self.link_doctype,
				"link_name": self.link_name,
				"name": ("!=", self.name or ""),
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("{0} is already linked to {1} ({2}).").format(
					frappe.bold(self.link_name), frappe.bold(self.activity), existing
				),
				title=_("Duplicate Link"),
				exc=frappe.DuplicateEntryError,
			)


def on_doctype_update():
	# `validate_duplicate` is the user-facing check, but this DocType is named by hash, so
	# nothing in the primary key stops two concurrent `add_link` calls from racing past it.
	# (The other EGC doctypes get this for free: their names are `{project}-{code}`, so the
	# primary key already enforces per-project uniqueness.)
	frappe.db.add_unique(
		"EGC Activity Link",
		["activity", "link_doctype", "link_name"],
		constraint_name="unique_activity_link_target",
	)
