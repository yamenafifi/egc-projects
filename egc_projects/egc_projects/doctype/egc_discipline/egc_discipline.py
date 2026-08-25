# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EGCDiscipline(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		description: DF.SmallText | None
		discipline_code: DF.Data
		discipline_name: DF.Data
		enabled: DF.Check
	# end: auto-generated types

	def before_naming(self) -> None:
		# `field:discipline_code` derives `name` from this value at naming time, which runs
		# before `validate()` — normalise here too so `name` is never out of sync with the
		# uppercased field.
		self._normalize_code()

	def validate(self) -> None:
		self._normalize_code()
		if self.discipline_name:
			self.discipline_name = self.discipline_name.strip()

	def _normalize_code(self) -> None:
		if self.discipline_code:
			self.discipline_code = self.discipline_code.strip().upper()
