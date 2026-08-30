"""Small resolvers for "given this Contact, what's its linked Customer / primary email / primary
phone" — needed by every controller that mirrors a Contact's info onto its own record
(`EGC Project Stakeholder`, `EGC Assignment`, ...) now that party identity is core `Contact`
rather than the old `EGC Person` (which carried `organization`/`email`/`phone` as flat fields
directly on itself).

No generic Frappe helper does this (confirmed by research — `address_and_contact.set_link_title`
only retitles existing `links` rows, it doesn't resolve them). These are plain, direct queries,
matching this app's own style elsewhere rather than a framework.
"""

from __future__ import annotations

import frappe


def get_linked_customer(contact: str) -> str | None:
	"""The Customer this Contact's `links` table points at, or None if it has no such link (or
	points at more than one — the first is used; a Contact meant to represent one party's person
	is expected to carry at most one Customer link in this app's usage)."""
	if not contact:
		return None
	return frappe.db.get_value(
		"Dynamic Link", {"parenttype": "Contact", "parent": contact, "link_doctype": "Customer"}, "link_name"
	)


def get_primary_email(contact: str) -> str | None:
	"""This Contact's primary email, or its first email if none is flagged primary."""
	if not contact:
		return None
	return frappe.db.get_value(
		"Contact Email", {"parenttype": "Contact", "parent": contact}, "email_id", order_by="is_primary desc"
	)


def get_primary_phone(contact: str) -> str | None:
	"""This Contact's primary phone, or its first phone if none is flagged primary. Prefers a
	number flagged `is_primary_phone` over one only flagged `is_primary_mobile_no` — matches
	Contact's own `phone`/`mobile_no` fetch precedence (contact.py `update_phone_numbers`)."""
	if not contact:
		return None
	return frappe.db.get_value(
		"Contact Phone",
		{"parenttype": "Contact", "parent": contact},
		"phone",
		order_by="is_primary_phone desc, is_primary_mobile_no desc",
	)
