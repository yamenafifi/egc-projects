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
		originator: DF.Data | None
		project: DF.Link
		revision_history_html: DF.HTML | None
		title: DF.Data
		wbs_node: DF.Link | None
	# end: auto-generated types

	def validate(self):
		validators.validate_unique_in_project(self, "document_number", _("Document"))
		validators.validate_same_project(self, "wbs_node", "EGC WBS Node", _("WBS Node"))


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
			"superseded_by",
		],
		order_by="revision_seq desc",
	)
	for row in rows:
		row["is_current"] = row.name == current_revision
	return rows
