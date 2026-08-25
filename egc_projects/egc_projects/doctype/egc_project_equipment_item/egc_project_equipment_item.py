# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EGCProjectEquipmentItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		commissioning_target: DF.Date | None
		department: DF.Data | None
		equipment_delivery_target: DF.Date | None
		equipment_manufacturer: DF.Link | None
		equipment_model: DF.Data | None
		facility: DF.Data | None
		modality: DF.Link | None
		notes: DF.SmallText | None
		oem_installation_target: DF.Date | None
		oem_reference: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		room_ready_target: DF.Date | None
		wbs_node: DF.Link | None
	# end: auto-generated types
