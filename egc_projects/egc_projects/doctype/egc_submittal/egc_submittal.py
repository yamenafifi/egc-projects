# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from egc_projects.egc_projects import code_naming, submittal_control, validators


class EGCSubmittal(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		current_due_date: DF.Date | None
		current_submission: DF.Link | None
		current_submission_label: DF.Data | None
		description: DF.SmallText | None
		discipline: DF.Link | None
		last_response_date: DF.Date | None
		project: DF.Link
		received_from: DF.Data | None
		received_from_person: DF.Link | None
		responsible_organization: DF.Link | None
		responsible_party: DF.Data | None
		submission_history_html: DF.HTML | None
		submittal_number: DF.Data
		submittal_status: DF.Literal[
			"Draft",
			"Submitted",
			"Under Review",
			"Approved",
			"Approved with Comments",
			"Revise & Resubmit",
			"Rejected",
		]
		submittal_type: DF.Link
		title: DF.Data
		wbs_node: DF.Link | None
	# end: auto-generated types

	def before_insert(self):
		# Only when blank — a bulk-imported row's own pre-existing code (e.g. a client's real
		# legacy numbering) is never overwritten; only genuinely new, code-less rows get one
		# assigned. By the time this runs, submit_for_review_flow.js has already resolved
		# submittal_type (picked or inferred from the chosen documents), so inference and
		# auto-numbering compose correctly. See code_naming.py's module docstring.
		if not self.submittal_number:
			code = code_naming.assign_submittal_code(self.project, self.discipline, self.submittal_type)
			if code:
				self.submittal_number = code

	def validate(self):
		validators.validate_unique_in_project(self, "submittal_number", _("Submittal"))
		validators.validate_same_project(self, "wbs_node", "EGC WBS Node", _("WBS Node"))
		self.fetch_from_directory()

	def fetch_from_directory(self):
		"""Level 1 §30: once a Directory reference is set, the matching free-text field always
		mirrors it — same discipline as `EGCProjectStakeholder.fetch_from_person`. The free-text
		field stays directly editable only when no Directory reference is linked (a genuine
		one-off party not worth adding to the Directory)."""
		if self.responsible_organization:
			self.responsible_party = frappe.db.get_value(
				"Customer", self.responsible_organization, "customer_name"
			)
		if self.received_from_person:
			self.received_from = frappe.db.get_value("User", self.received_from_person, "full_name")


@frappe.whitelist()
def get_submissions(submittal: str) -> list[dict]:
	"""Every submission/review cycle of `submittal`, newest first, with the documents it carried.

	Used by `egc_submittal.js` to render the read-only submission history table. Every cycle
	stays visible forever — `create_next_revision` never overwrites or hides an earlier one.
	"""
	frappe.has_permission("EGC Submittal", "read", doc=submittal, throw=True)

	current_submission = submittal_control.get_current_submission(submittal)
	rows = frappe.get_all(
		"EGC Submittal Revision",
		filters={"submittal": submittal},
		fields=[
			"name",
			"revision_label",
			"submission_seq",
			"docstatus",
			"date_submitted",
			"due_date",
			"submitted_by",
			"reviewer",
			"submission_status",
			"response",
			"response_date",
			"responded_by",
			"response_remarks",
		],
		order_by="submission_seq desc",
	)
	for row in rows:
		row["is_current"] = row.name == current_submission
		row["documents"] = frappe.get_all(
			"EGC Submittal Document Item",
			filters={"parent": row.name},
			fields=["document_revision", "document", "revision", "document_title"],
			order_by="idx",
		)
	return rows
