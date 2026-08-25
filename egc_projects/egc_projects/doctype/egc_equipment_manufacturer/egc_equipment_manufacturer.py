# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EGCEquipmentManufacturer(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		enabled: DF.Check
		manufacturer_name: DF.Data
	# end: auto-generated types

	def before_naming(self) -> None:
		self._normalize_name()

	def validate(self) -> None:
		self._normalize_name()

	def _normalize_name(self) -> None:
		if self.manufacturer_name:
			self.manufacturer_name = self.manufacturer_name.strip()
