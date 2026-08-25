# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from egc_projects.egc_projects import validators


class EGCProjectProfile(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from egc_projects.egc_projects.doctype.egc_project_equipment_item.egc_project_equipment_item import (
			EGCProjectEquipmentItem,
		)
		from egc_projects.egc_projects.doctype.egc_project_stakeholder.egc_project_stakeholder import (
			EGCProjectStakeholder,
		)

		address: DF.SmallText | None
		city: DF.Data | None
		commissioning_target: DF.Date | None
		contract_date: DF.Date | None
		contract_type: DF.Literal["", "Lump Sum", "Unit Price", "Cost Plus", "Time & Material", "Other"]
		contract_value: DF.Currency
		country: DF.Link | None
		delivery_method: DF.Literal[
			"", "Design-Bid-Build", "Design-Build", "EPC", "Turnkey", "Other"
		]
		dlp_end_date: DF.Date | None
		equipment_items: DF.Table[EGCProjectEquipmentItem]
		forecast_completion_date: DF.Date | None
		latitude: DF.Float
		longitude: DF.Float
		project: DF.Link
		project_code: DF.Data | None
		project_description: DF.SmallText | None
		project_image: DF.AttachImage | None
		project_stage: DF.Literal[
			"", "Design", "Procurement", "Construction", "Commissioning", "Closeout", "Warranty"
		]
		region: DF.Data | None
		sector: DF.Literal["", "Healthcare", "Industrial", "Commercial", "Infrastructure", "Other"]
		site_contact_email: DF.Data | None
		site_contact_name: DF.Data | None
		site_contact_phone: DF.Data | None
		stakeholders: DF.Table[EGCProjectStakeholder]
		time_zone: DF.Data | None
		warranty_start_date: DF.Date | None
		work_scope: DF.TextEditor | None
	# end: auto-generated types

	def validate(self) -> None:
		# `field:project` autoname already guarantees the 1:1 mapping; this is the defensive
		# check called out in ARCHITECTURE_V2.md §1 for a `project` value that doesn't exist.
		if not self.project or not frappe.db.exists("Project", self.project):
			frappe.throw(_("Project {0} does not exist.").format(frappe.bold(self.project or "")))

		self._validate_equipment_items()

	def _validate_equipment_items(self) -> None:
		for row in self.equipment_items:
			if not row.wbs_node:
				continue
			# `EGC Project Equipment Item` has no `project` field of its own — set it on the
			# in-memory row so the shared validator can anchor against the Profile's project,
			# per ARCHITECTURE_V2.md §1 ("no new validation pattern invented").
			row.project = self.project
			validators.validate_same_project(row, "wbs_node", "EGC WBS Node", _("WBS Node"))
