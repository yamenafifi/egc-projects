# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from egc_projects.egc_projects import validators


class EGCDrawingSet(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		description: DF.SmallText | None
		issue_date: DF.Date | None
		project: DF.Link
		sequence: DF.Int
		set_code: DF.Data
		set_name: DF.Data
	# end: auto-generated types

	def validate(self) -> None:
		validators.validate_unique_in_project(self, "set_code", "Set Code")
