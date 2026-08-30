# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from egc_projects.egc_projects import directory


class EGCProjectStakeholder(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		email: DF.Data | None
		is_primary: DF.Check
		organization: DF.Link | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		party_name: DF.Data
		person: DF.Link | None
		phone: DF.Data | None
		role: DF.Link
		user: DF.Link | None
	# end: auto-generated types

	def validate(self):
		self.fetch_from_person()

	def fetch_from_person(self):
		"""The normal path (§30 of the Level 0 directory expansion): once `person` is set, this
		row's own display fields always mirror the Directory record rather than drifting into an
		independent copy — the free-text fields stay directly editable ONLY for a genuine one-off
		party that isn't in the Directory (`person` left blank)."""
		if not self.person:
			return
		contact = frappe.db.get_value("Contact", self.person, ["full_name", "user"], as_dict=True)
		if not contact:
			return
		self.party_name = contact.full_name
		self.organization = directory.get_linked_customer(self.person)
		self.user = contact.user
		self.email = directory.get_primary_email(self.person)
		self.phone = directory.get_primary_phone(self.person)
