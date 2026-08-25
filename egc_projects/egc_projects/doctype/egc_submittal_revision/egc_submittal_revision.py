# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import submittal_control, validators


class EGCSubmittalRevision(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from egc_projects.egc_projects.doctype.egc_submittal_document_item.egc_submittal_document_item import (
			EGCSubmittalDocumentItem,
		)
		from frappe.types import DF

		date_submitted: DF.Date | None
		documents: DF.Table[EGCSubmittalDocumentItem]
		due_date: DF.Date | None
		project: DF.Link | None
		response: DF.Literal["", "Approved", "Approved with Comments", "Revise & Resubmit", "Rejected"]
		response_date: DF.Date | None
		response_remarks: DF.Text | None
		responded_by: DF.Link | None
		reviewer: DF.Link | None
		revision_label: DF.Data
		submission_seq: DF.Int
		submission_status: DF.Literal["Draft", "Submitted", "Under Review", "Responded", "Cancelled"]
		submittal: DF.Link
		submitted_by: DF.Link | None
	# end: auto-generated types

	def before_insert(self):
		# System-set ordering authority; never trust a client-supplied value.
		self.submission_seq = submittal_control.next_submission_seq(self.submittal)
		self.submission_status = c.SUBMISSION_DRAFT
		self.response = None
		self.response_date = None
		self.responded_by = None
		self.response_remarks = None

	def after_insert(self):
		# hooks.py only wires on_submit/on_cancel/on_trash; a fresh Draft still has to appear as
		# the submittal's current submission immediately, so refresh here too.
		submittal_control.refresh_submittal_state(self.submittal)

	def validate(self):
		if not self.is_new():
			submittal_control.assert_engine_authorized(self)

		validators.validate_unique_under_parent(self, "submittal", "revision_label", _("Revision Label"))
		self._validate_documents()

	def before_submit(self):
		self._validate_ready_for_submission()

	def on_update_after_submit(self):
		submittal_control.assert_engine_authorized(self)

	def _validate_documents(self):
		project = self.project or validators.get_project_of("EGC Submittal", self.submittal)
		seen = set()
		for row in self.documents:
			if not row.document_revision:
				continue

			if row.document_revision in seen:
				frappe.throw(
					_("Document Revision {0} is attached more than once.").format(
						frappe.bold(row.document_revision)
					),
					title=_("Duplicate Document Revision"),
					exc=frappe.ValidationError,
				)
			seen.add(row.document_revision)

			revision_project = validators.get_project_of("EGC Project Document Revision", row.document_revision)
			if project and revision_project and revision_project != project:
				frappe.throw(
					_("Document Revision {0} belongs to project {1}, not {2}.").format(
						frappe.bold(row.document_revision),
						frappe.bold(revision_project),
						frappe.bold(project),
					),
					title=_("Cross-Project Link Rejected"),
				)

			# `document`/`revision` are fetch_from'd automatically before validate() runs;
			# `document_title` needs a second hop (document_revision.document.title), so it is
			# set here rather than via fetch_from.
			if row.document and not row.document_title:
				row.document_title = frappe.db.get_value("EGC Project Document", row.document, "title")

	def _validate_ready_for_submission(self):
		if not self.documents:
			frappe.throw(
				_("At least one document revision must be attached before {0} can be submitted for review.").format(
					frappe.bold(self.name)
				),
				title=_("Nothing to Submit"),
				exc=frappe.ValidationError,
			)

		for row in self.documents:
			revision = frappe.db.get_value(
				"EGC Project Document Revision",
				row.document_revision,
				["docstatus", "revision_status"],
				as_dict=True,
			)
			if not revision or revision.docstatus != 1 or revision.revision_status != c.REVISION_ISSUED:
				frappe.throw(
					_(
						"Document Revision {0} is not an Issued revision and cannot be submitted for review."
					).format(frappe.bold(row.document_revision)),
					title=_("Not Allowed"),
					exc=frappe.ValidationError,
				)
