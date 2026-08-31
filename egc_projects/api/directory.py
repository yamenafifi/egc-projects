"""Whitelisted API behind the Hub's Directory tab.

Surfaces every `EGC Project Stakeholder` row for a project (already the "pick a Project
Directory entry" data source several other dialogs across this app use) as a real, actionable
list — who's on this project, their role, and whether they can log in and see it (Portal
Access). Portal access itself is nothing new: it's the same read-only "EGC External Viewer"
role + User-Permission-scoped-to-one-Project pattern already proven in
`tests/test_external_viewer.py`, just made reachable from the Hub instead of requiring a System
Manager to wire it up by hand from the Desk.

A client-side submittal REVIEWER is not a separate access tier from a client-side VIEWER:
`record_step_response` (submittal_control.py) authorizes purely by identity — "are you the
assigned reviewer_user" — not by doctype role permission (confirmed by reading that function
directly, not assumed), so granting `EGC External Viewer` is already everything an external
reviewer needs to both see a Submittal and respond to a step assigned to them. No separate
"reviewer" role exists here or is needed.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.permissions import add_user_permission, remove_user_permission

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import project_profile, validators

#: Roles a Directory entry can be granted Portal Access under, with what each one means —
#: surfaced in the Hub's Grant Portal Access dialog rather than free-typing a role name in.
GRANTABLE_ROLES = (
	(c.ROLE_PROJECT_MANAGER, "Internal — full project management access"),
	(c.ROLE_PROJECT_ENGINEER, "Internal — engineering access"),
	(c.ROLE_DOCUMENT_CONTROLLER, "Internal — document control access"),
	(c.ROLE_PROJECT_VIEWER, "Internal — read-only access"),
	(c.ROLE_EXTERNAL_VIEWER, "External — read-only access, and can respond to Submittal steps assigned to them"),
)


def _has_portal_access(user: str | None, project: str) -> bool:
	if not user:
		return False
	return bool(frappe.db.exists("User Permission", {"user": user, "allow": "Project", "for_value": project}))


@frappe.whitelist()
def get_directory(project: str) -> list[dict]:
	validators.require_project_permission(project)

	rows = project_profile.get_stakeholders(project)
	role_names = list({row.role for row in rows if row.role})
	internal_by_role = (
		{
			r.name: r.is_egc_internal
			for r in frappe.get_all(
				"EGC Stakeholder Role", filters={"name": ("in", role_names)}, fields=["name", "is_egc_internal"]
			)
		}
		if role_names
		else {}
	)
	# `row.organization` is a Dynamic Link (Customer or Supplier, per `row.organization_type`) —
	# neither doctype's Link value is presentable on its own (naming_series-based), so fetch each
	# one's display name (customer_name/supplier_name) for the table; the raw Link value stays
	# `row.organization` for the Change Organization dialog etc.
	customer_names = _display_names("Customer", "customer_name", rows)
	supplier_names = _display_names("Supplier", "supplier_name", rows)

	for row in rows:
		row["is_egc_internal"] = bool(internal_by_role.get(row.role))
		# `person` links directly to a User now — no separate identity record to resolve through.
		row["has_portal_access"] = _has_portal_access(row.person, project)
		row["portal_roles"] = [r for r in frappe.get_roles(row.person) if r in c.EGC_ROLES] if row.person else []
		if row.organization_type == "Supplier":
			row["organization_name"] = supplier_names.get(row.organization)
		else:
			row["organization_name"] = customer_names.get(row.organization)

	return rows


def _display_names(doctype: str, name_field: str, rows: list[dict]) -> dict[str, str]:
	names = {row.organization for row in rows if row.organization and row.organization_type == doctype}
	if not names:
		return {}
	return {
		r.name: r.get(name_field)
		for r in frappe.get_all(doctype, filters={"name": ("in", list(names))}, fields=["name", name_field])
	}


@frappe.whitelist()
def grant_portal_access(project: str, row_name: str, role: str, email: str | None = None) -> dict:
	"""Grants Hub access to the person behind Directory row `row_name` — creating their `User`
	first if they don't have one yet (via `email`, reusing an existing `User` of that address if
	one exists), then assigning `role` and scoping them to `project` with a `User Permission`
	(the same mechanism `test_external_viewer.py` already proves out; nothing new here). `person`
	links directly to a User (no separate identity record), so a newly created User only needs to
	be mirrored onto this one row's `person` field."""
	validators.require_project_permission(project, "write")
	if role not in dict(GRANTABLE_ROLES):
		frappe.throw(_("{0} is not a grantable role.").format(role), exc=frappe.ValidationError)

	stakeholder = frappe.get_doc("EGC Project Stakeholder", row_name)
	if stakeholder.parenttype != "Project" or stakeholder.parent != project:
		frappe.throw(_("That Directory entry does not belong to this project."), exc=frappe.PermissionError)

	user = stakeholder.person
	if not user:
		if not email:
			frappe.throw(_("An email is required to create a login for this person."), exc=frappe.ValidationError)
		user = frappe.db.get_value("User", {"email": email})
		if not user:
			new_user = frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": stakeholder.party_name or email.split("@")[0],
					"send_welcome_email": 0,
				}
			)
			new_user.insert(ignore_permissions=True)
			user = new_user.name
		# `EGC Project Stakeholder` is a child table row (`istable: 1`, parenttype "Project") —
		# saving it standalone via a doc loaded straight off its own name is a no-op (Frappe
		# child rows persist through their PARENT's own save, not independently), so this goes
		# through `frappe.db.set_value` instead, the same direct-write approach the rest of this
		# app already uses for narrowly-scoped writes it has separately authorized above.
		frappe.db.set_value("EGC Project Stakeholder", row_name, "person", user)

	# Not `User.add_roles()` — it calls a plain `self.save()` with no bypass, and a Project
	# Manager granting scoped Hub access has no reason to also independently need write
	# permission on the core `User` doctype itself. `require_project_permission` above is the
	# real gate; this mirrors `add_roles()`'s own two lines with that already-checked authority.
	user_doc = frappe.get_doc("User", user)
	user_doc.append_roles(role)
	user_doc.save(ignore_permissions=True)

	is_first_grant = not _has_portal_access(user, project)
	add_user_permission("Project", project, user, ignore_permissions=True)

	if is_first_grant:
		from egc_projects.egc_projects import notifications

		notifications.send_directory_welcome_email(user, project)

	return {"user": user}


@frappe.whitelist()
def revoke_portal_access(project: str, user: str) -> None:
	"""Removes the `User Permission` scoping `user` to `project`. If that was their only
	remaining `Project` scope, also strips every EGC role they hold.

	This second step is not optional cleanup — it closes a real privilege-escalation hole.
	Frappe's own `has_user_permission` returns `True` unconditionally for a user with ZERO
	`User Permission` rows for a doctype (confirmed directly against `frappe/permissions.py`):
	an EGC role was only ever safe to hold *because* a `User Permission` scoped it to one
	Project. Removing their last scope while leaving the role behind would silently upgrade
	them from "sees one project" to "sees every project" the moment this function runs — the
	opposite of what "revoke" means. A user who still has a `User Permission` on another
	Project keeps their roles untouched; only the fully-unscoped case strips them."""
	validators.require_project_permission(project, "write")
	remove_user_permission("Project", project, user, ignore_permissions=True)

	if frappe.db.count("User Permission", {"user": user, "allow": "Project"}):
		return

	user_doc = frappe.get_doc("User", user)
	existing_roles = {d.role: d for d in user_doc.get("roles")}
	held_egc_roles = [existing_roles[role] for role in c.EGC_ROLES if role in existing_roles]
	if not held_egc_roles:
		return
	for row in held_egc_roles:
		user_doc.get("roles").remove(row)
	# Not `remove_roles()` — it ends in a plain `self.save()` with no permission bypass, and a
	# Project Manager revoking scoped Hub access has no reason to also independently need write
	# permission on the core `User` doctype. Same reasoning `grant_portal_access` already
	# documents for `append_roles`/explicit `ignore_permissions=True` above.
	user_doc.save(ignore_permissions=True)


@frappe.whitelist()
def update_stakeholder_role(project: str, row_name: str, role: str) -> None:
	validators.require_project_permission(project, "write")
	doc = frappe.get_doc("Project", project)
	row = next((r for r in doc.custom_egc_stakeholders if r.name == row_name), None)
	if not row:
		frappe.throw(_("Stakeholder row not found."), exc=frappe.DoesNotExistError)
	row.role = role
	doc.save()
