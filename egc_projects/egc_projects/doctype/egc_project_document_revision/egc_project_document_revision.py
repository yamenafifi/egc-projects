# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe import _
from frappe.model.document import Document

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import document_control, validators


class EGCProjectDocumentRevision(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		document: DF.Link
		file: DF.Attach
		issue_date: DF.Date | None
		project: DF.Link | None
		readiness: DF.Literal["Uploaded", "Reviewed", "Ready to Publish"]
		reason_for_revision: DF.Data | None
		remarks: DF.SmallText | None
		revision: DF.Data
		revision_date: DF.Date
		revision_seq: DF.Int
		revision_status: DF.Literal["Draft", "Issued", "Superseded", "Cancelled"]
		superseded_by: DF.Link | None
	# end: auto-generated types

	def before_insert(self):
		# System-set ordering authority; never trust a client-supplied value.
		self.revision_seq = document_control.next_revision_seq(self.document)
		self.revision_status = c.REVISION_DRAFT
		self.superseded_by = None

	def after_insert(self):
		# hooks.py only wires on_submit/on_cancel/on_trash; a fresh Draft still has to flip
		# the document from "No Revision" to "Draft" immediately, so refresh here too.
		document_control.refresh_document_state(self.document)

	def validate(self):
		if not self.is_new():
			document_control.assert_engine_authorized(self)

		validators.validate_same_project(self, "document", "EGC Project Document", _("Document"))
		validators.validate_unique_under_parent(self, "document", "revision", _("Revision"))

	def on_update_after_submit(self):
		document_control.assert_engine_authorized(self)
