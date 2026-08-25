# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EGCDocumentType(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		abbreviation: DF.Data | None
		description: DF.SmallText | None
		document_type_name: DF.Data
		enabled: DF.Check
		is_drawing: DF.Check
	# end: auto-generated types

	def before_naming(self) -> None:
		# `field:document_type_name` derives `name` from this value at naming time, which
		# runs before `validate()` — strip here too so `name` is never out of sync.
		self._normalize_name()

	def validate(self) -> None:
		self._normalize_name()

	def _normalize_name(self) -> None:
		if self.document_type_name:
			self.document_type_name = self.document_type_name.strip()
