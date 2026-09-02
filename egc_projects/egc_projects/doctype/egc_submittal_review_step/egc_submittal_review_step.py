# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""An INSTANTIATED per-submission review step (docs/ARCHITECTURE_V2.md §7). Never edited by a
template change after creation — `EGC Submittal Workflow Template` is a convenience for
generating these rows, not a live binding to them.

`status`, `response`, `response_date`, `responded_by`, `response_remarks`, `response_attachment`
are engine-owned — see `submittal_control.py`'s `assert_step_engine_authorized`, the same
discipline as every other engine-guarded field in this app.
"""

from frappe.model.document import Document


class EGCSubmittalReviewStep(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		is_required: DF.Check
		origin: DF.Literal["Pre-Planned", "Forwarded"]
		project: DF.Link
		response: DF.Literal["", "Approved", "Approved with Comments", "Revise & Resubmit", "Rejected"]
		responded_by: DF.Link | None
		response_attachment: DF.Attach | None
		response_date: DF.Date | None
		response_remarks: DF.SmallText | None
		reviewer_label: DF.Data | None
		reviewer_role: DF.Link | None
		reviewer_user: DF.Link | None
		sequence: DF.Int
		status: DF.Literal["Pending", "In Review", "Responded", "Skipped"]
		submittal_revision: DF.Link
	# end: auto-generated types

	def validate(self):
		# Not submittable (docstatus always 0) — the engine guard therefore only needs to run on
		# every save after creation, unlike document_control.py's `on_update_after_submit`
		# variant, which exists for a genuinely submittable doctype.
		if not self.is_new():
			from egc_projects.egc_projects import submittal_control

			submittal_control.assert_step_engine_authorized(self)
