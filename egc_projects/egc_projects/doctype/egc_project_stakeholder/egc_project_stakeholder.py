# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EGCProjectStakeholder(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		contact: DF.Link | None
		email: DF.Data | None
		is_primary: DF.Check
		organization: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		party_name: DF.Data
		phone: DF.Data | None
		role: DF.Link
		user: DF.Link | None
	# end: auto-generated types
