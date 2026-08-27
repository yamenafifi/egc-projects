# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EGCOrganization(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		address: DF.SmallText | None
		contact_email: DF.Data | None
		contact_phone: DF.Data | None
		description: DF.SmallText | None
		enabled: DF.Check
		organization_name: DF.Data
		organization_type: DF.Literal[
			"", "Client", "Main Contractor", "Consultant", "Architect", "OEM", "Subcontractor", "Supplier", "Specialist Vendor", "Other"
		]
	# end: auto-generated types
