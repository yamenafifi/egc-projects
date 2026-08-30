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

	for row in rows:
		row["is_egc_internal"] = bool(internal_by_role.get(row.role))
		row["has_portal_access"] = _has_portal_access(row.user, project)
		row["portal_roles"] = [r for r in frappe.get_roles(row.user) if r in c.EGC_ROLES] if row.user else []

	return rows


@frappe.whitelist()
def grant_portal_access(project: str, row_name: str, role: str, email: str | None = None) -> dict:
	"""Grants Hub access to the person behind Directory row `row_name` — creating their `User`
	first if they don't have one yet (via `email`, reusing an existing `User` of that address
	if one exists), then assigning `role` and scoping them to `project` with a `User Permission`
	(the same mechanism `test_external_viewer.py` already proves out; nothing new here). A newly
	created `User` is mirrored back onto the stakeholder row — and its `EGC Person`, if linked —
	the same "normal path" `EGC Project Stakeholder` already documents."""
	validators.require_project_permission(project, "write")
	if role not in dict(GRANTABLE_ROLES):
		frappe.throw(_("{0} is not a grantable role.").format(role), exc=frappe.ValidationError)

	stakeholder = frappe.get_doc("EGC Project Stakeholder", row_name)
	if stakeholder.parenttype != "Project" or stakeholder.parent != project:
		frappe.throw(_("That Directory entry does not belong to this project."), exc=frappe.PermissionError)

	user = stakeholder.user
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
		frappe.db.set_value("EGC Project Stakeholder", row_name, "user", user)
		if stakeholder.person:
			person = frappe.get_doc("EGC Person", stakeholder.person)
			if not person.user:
				person.user = user
				person.save(ignore_permissions=True)

	# Not `User.add_roles()` — it calls a plain `self.save()` with no bypass, and a Project
	# Manager granting scoped Hub access has no reason to also independently need write
	# permission on the core `User` doctype itself. `require_project_permission` above is the
	# real gate; this mirrors `add_roles()`'s own two lines with that already-checked authority.
	user_doc = frappe.get_doc("User", user)
	user_doc.append_roles(role)
	user_doc.save(ignore_permissions=True)
	add_user_permission("Project", project, user, ignore_permissions=True)
	return {"user": user}


@frappe.whitelist()
def revoke_portal_access(project: str, user: str) -> None:
	"""Removes the `User Permission` scoping `user` to `project` — leaves the `User` account
	itself, and any roles it holds, untouched. A separate, more destructive "disable this
	person's login entirely" action is out of scope here; this is specifically "they no longer
	see THIS project," which is the Directory's own concern."""
	validators.require_project_permission(project, "write")
	remove_user_permission("Project", project, user, ignore_permissions=True)


@frappe.whitelist()
def update_stakeholder_role(project: str, row_name: str, role: str) -> None:
	validators.require_project_permission(project, "write")
	doc = frappe.get_doc("Project", project)
	row = next((r for r in doc.custom_egc_stakeholders if r.name == row_name), None)
	if not row:
		frappe.throw(_("Stakeholder row not found."), exc=frappe.DoesNotExistError)
	row.role = role
	doc.save()
