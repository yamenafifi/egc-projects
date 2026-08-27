# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class EGCPerson(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		email: DF.Data | None
		enabled: DF.Check
		full_name: DF.Data
		organization: DF.Link | None
		phone: DF.Data | None
		title: DF.Data | None
		user: DF.Link | None
	# end: auto-generated types

	def validate(self):
		self._validate_user_not_already_a_different_person()
		self._fetch_email_from_user_if_blank()

	def _validate_user_not_already_a_different_person(self):
		# A User maps to at most one Person — otherwise "who is this User in the Directory"
		# becomes ambiguous everywhere a Person is resolved from a logged-in user.
		if not self.user:
			return
		existing = frappe.db.get_value(
			"EGC Person", {"user": self.user, "name": ("!=", self.name or "")}, "name"
		)
		if existing:
			frappe.throw(
				_("User {0} is already the Person {1}.").format(frappe.bold(self.user), existing),
				title=_("Already Linked"),
				exc=frappe.ValidationError,
			)

	def _fetch_email_from_user_if_blank(self):
		if self.user and not self.email:
			self.email = frappe.db.get_value("User", self.user, "email")
