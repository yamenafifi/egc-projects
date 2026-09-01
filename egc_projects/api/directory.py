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


def _has_bypass_role(user: str | None) -> bool:
	"""True for System Manager / Projects Manager (`constants.PROJECT_VISIBILITY_BYPASS_ROLES`) —
	holders see every project unconditionally, so `grant_portal_access` must never scope them with
	a `Project` User Permission (Frappe's own User Permission enforcement has no role-based
	bypass: the moment even one row exists for `allow="Project"`, that user is restricted to only
	the allowed value(s), regardless of role — confirmed against `frappe/permissions.py`)."""
	if not user:
		return False
	return bool(set(frappe.get_roles(user)) & set(c.PROJECT_VISIBILITY_BYPASS_ROLES))


def _has_portal_access(user: str | None, project: str) -> bool:
	if not user:
		return False
	if _has_bypass_role(user):
		return True
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

	# Both used to run once PER ROW (`_has_portal_access` + `frappe.get_roles`) — a real N+1 on
	# every Directory-tab load. Batched here: one query each for the whole page of stakeholders.
	persons = list({row.person for row in rows if row.person})
	portal_access_users = (
		set(
			frappe.get_all(
				"User Permission",
				filters={"user": ("in", persons), "allow": "Project", "for_value": project},
				pluck="user",
			)
		)
		if persons
		else set()
	)
	portal_roles_by_person: dict[str, list[str]] = {}
	bypass_persons: set[str] = set()
	if persons:
		for row in frappe.get_all(
			"Has Role",
			filters={"parent": ("in", persons), "role": ("in", list(c.EGC_ROLES))},
			fields=["parent", "role"],
		):
			portal_roles_by_person.setdefault(row.parent, []).append(row.role)
		bypass_persons = set(
			frappe.get_all(
				"Has Role",
				filters={"parent": ("in", persons), "role": ("in", list(c.PROJECT_VISIBILITY_BYPASS_ROLES))},
				pluck="parent",
			)
		)

	for row in rows:
		row["is_egc_internal"] = bool(internal_by_role.get(row.role))
		# `person` links directly to a User now — no separate identity record to resolve through.
		# A bypass-role holder (System Manager/Projects Manager) is never given a scoping User
		# Permission (see grant_portal_access), so they'd otherwise always read as "No login"/"no
		# access" here despite genuinely seeing every project — `is_admin_bypass` lets the UI show
		# what's actually true instead.
		row["is_admin_bypass"] = row.person in bypass_persons
		row["has_portal_access"] = row.person in portal_access_users or row["is_admin_bypass"]
		row["portal_roles"] = portal_roles_by_person.get(row.person, [])
		if row.organization_type == "Other":
			# A deliberately ad-hoc organization — never a Customer/Supplier record, so there's
			# nothing to look up; the free-text label the user typed IS the display name.
			row["organization_name"] = row.organization_label
		elif row.organization_type == "Supplier":
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
def grant_portal_access(project: str, row_name: str, email: str | None = None) -> dict:
	"""Grants Hub access to the person behind Directory row `row_name` — creating their `User`
	first if they don't have one yet (via `email`, reusing an existing `User` of that address if
	one exists), then scoping them to `project` with a `User Permission` (the same mechanism
	`test_external_viewer.py` already proves out; nothing new here). `person` links directly to a
	User (no separate identity record), so a newly created User only needs to be mirrored onto
	this one row's `person` field.

	Does exactly one thing beyond that: gives the person visibility into this project. It does
	NOT let the caller pick an arbitrary Frappe Role from a dropdown — direct instruction, after
	the previous version's manual role-pick conflated "who is this person" (Stakeholder Role) with
	"what can they do" (permission Role) and, combined with unconditional User Permission scoping,
	caused a real regression: an admin (System Manager) granting themselves access lost visibility
	of every other project. Whatever roles this person's Stakeholder Role template implies are
	applied automatically (`project_profile.sync_roles_from_stakeholder_role`, additive-only), and
	a bypass-role holder (`constants.PROJECT_VISIBILITY_BYPASS_ROLES`) is never scoped with a User
	Permission at all — they already see everything; adding one would only ever narrow them."""
	validators.require_project_permission(project, "write")

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

	project_profile.sync_roles_from_stakeholder_role(user, stakeholder.role)

	is_first_grant = not _has_portal_access(user, project)
	if not _has_bypass_role(user):
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
	# A bypass-role holder (System Manager/Projects Manager) never got a scoping row in the first
	# place (grant_portal_access skips it for them) — `remove_user_permission` looks the row up by
	# (user, allow, for_value) and hands `frappe.delete_doc` a bare `None` name if nothing matches,
	# which raises rather than no-opping. Guard explicitly instead of assuming a row exists.
	if frappe.db.exists("User Permission", {"user": user, "allow": "Project", "for_value": project}):
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
	project_profile.sync_roles_from_stakeholder_role(row.person, role)
