# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from egc_projects.egc_projects import document_control, validators


class EGCProjectDocument(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		approval_status: DF.Literal[
			"Not Submitted",
			"Under Review",
			"Approved",
			"Approved with Comments",
			"Revise & Resubmit",
			"Rejected",
		]
		current_file: DF.Attach | None
		current_revision: DF.Link | None
		current_revision_date: DF.Date | None
		current_revision_label: DF.Data | None
		description: DF.SmallText | None
		discipline: DF.Link | None
		document_number: DF.Data
		document_status: DF.Literal["No Revision", "Draft", "Issued", "Cancelled"]
		document_type: DF.Link
		drawing_area: DF.Link | None
		drawing_date: DF.Date | None
		drawing_set: DF.Link | None
		originator: DF.Data | None
		originator_person: DF.Link | None
		project: DF.Link
		received_date: DF.Date | None
		revision_history_html: DF.HTML | None
		title: DF.Data
		wbs_node: DF.Link | None
	# end: auto-generated types

	def validate(self):
		validators.validate_unique_in_project(self, "document_number", _("Document"))
		validators.validate_same_project(self, "wbs_node", "EGC WBS Node", _("WBS Node"))
		validators.validate_same_project(self, "drawing_set", "EGC Drawing Set", _("Drawing Set"))
		validators.validate_same_project(self, "drawing_area", "EGC Drawing Area", _("Drawing Area"))
		self.fetch_from_directory()

	def fetch_from_directory(self):
		"""Level 1 §30/§33: once `originator_person` is set, Originator always mirrors it — same
		discipline as `EGCProjectStakeholder.fetch_from_person` and `EGCSubmittal.fetch_from_
		directory`. Stays directly editable only when no Directory reference is linked."""
		if self.originator_person:
			self.originator = frappe.db.get_value("Contact", self.originator_person, "full_name")


@frappe.whitelist()
def get_revisions(document: str) -> list[dict]:
	"""Every revision of `document`, newest first, with the current one flagged.

	Used by `egc_project_document.js` to render the read-only revision history table.
	"""
	frappe.has_permission("EGC Project Document", "read", doc=document, throw=True)

	current_revision = document_control.get_current_revision(document)
	rows = frappe.get_all(
		"EGC Project Document Revision",
		filters={"document": document},
		fields=[
			"name",
			"revision",
			"revision_seq",
			"revision_status",
			"docstatus",
			"file",
			"revision_date",
			"issue_date",
			"remarks",
			"readiness",
			"superseded_by",
		],
		order_by="revision_seq desc",
	)
	for row in rows:
		row["is_current"] = row.name == current_revision
	return rows
