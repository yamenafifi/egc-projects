# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EGCModality(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		enabled: DF.Check
		modality_name: DF.Data
	# end: auto-generated types

	def before_naming(self) -> None:
		self._normalize_name()

	def validate(self) -> None:
		self._normalize_name()

	def _normalize_name(self) -> None:
		if self.modality_name:
			self.modality_name = self.modality_name.strip()
