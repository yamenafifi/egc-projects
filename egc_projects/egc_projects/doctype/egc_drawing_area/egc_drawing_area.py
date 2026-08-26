# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from egc_projects.egc_projects import validators


class EGCDrawingArea(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		area_code: DF.Data
		area_name: DF.Data
		description: DF.SmallText | None
		project: DF.Link
		sequence: DF.Int
		wbs_node: DF.Link | None
	# end: auto-generated types

	def validate(self) -> None:
		validators.validate_unique_in_project(self, "area_code", "Area Code")
		validators.validate_same_project(self, "wbs_node", "EGC WBS Node", "WBS Node")
