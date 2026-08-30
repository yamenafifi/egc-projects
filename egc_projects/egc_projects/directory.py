"""Resolves a User's organization via ERPNext's own native "Portal User" mechanism — the
`portal_users` child table (options `Portal User`) that already exists on both core `Customer`
and `Supplier`. A person in this app's Directory IS a User (their login is their identity — no
separate Contact/Person record); if that User is a Portal User of a Customer or Supplier, that's
their organization, otherwise they're EGC-internal.

No generic Frappe/ERPNext helper does this parameterized by an arbitrary user — the closest
native equivalent, `website_list_for_contact.get_parents_for_user`, is hardcoded to
`frappe.session.user`. This is a small, direct query in the same style, just parameterized.
"""

from __future__ import annotations

import frappe


def resolve_organization(user: str) -> tuple[str, str] | None:
	"""(doctype, name) of the Customer or Supplier `user` is a Portal User of, or None if they're
	linked to neither (EGC-internal)."""
	if not user:
		return None
	rows = frappe.get_all(
		"Portal User",
		filters={"user": user, "parenttype": ("in", ["Customer", "Supplier"])},
		fields=["parent", "parenttype"],
		limit=1,
	)
	return (rows[0].parenttype, rows[0].parent) if rows else None
