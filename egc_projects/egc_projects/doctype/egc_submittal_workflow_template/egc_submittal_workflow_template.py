# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""A reusable named review sequence (docs/ARCHITECTURE_V2.md §7 — "Standard Consultant Review",
"Siemens Material Approval"). Applying a template to a submission COPIES its steps into
`EGC Submittal Review Step` rows; a later edit to the template never retroactively changes a
submission that already applied it — the template is a convenience for creating steps, not a
live binding.
"""

import frappe
from frappe.model.document import Document


class EGCSubmittalWorkflowTemplate(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from egc_projects.egc_projects.doctype.egc_submittal_workflow_template_step.egc_submittal_workflow_template_step import (
			EGCSubmittalWorkflowTemplateStep,
		)

		description: DF.SmallText | None
		steps: DF.Table[EGCSubmittalWorkflowTemplateStep]
		template_name: DF.Data
	# end: auto-generated types

	def validate(self):
		seen = set()
		for row in self.steps:
			key = (row.sequence, row.reviewer_role)
			if key in seen:
				frappe.throw(
					frappe._(
						"Step {0} already has {1} at sequence {2}."
					).format(row.idx, row.reviewer_role, row.sequence)
				)
			seen.add(key)
