# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EGCStakeholderRole(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		enabled: DF.Check
		is_egc_internal: DF.Check
		role_name: DF.Data
		sequence: DF.Int
	# end: auto-generated types

	def before_naming(self) -> None:
		# `field:role_name` derives `name` from this value at naming time, which runs before
		# `validate()` — normalise here too so `name` is never out of sync with the stripped
		# field, mirroring `EGC Discipline`.
		self._normalize_name()

	def validate(self) -> None:
		self._normalize_name()

	def _normalize_name(self) -> None:
		if self.role_name:
			self.role_name = self.role_name.strip()
