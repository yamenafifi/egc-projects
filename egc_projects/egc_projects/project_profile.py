"""Project Information domain helpers (ARCHITECTURE_V2.md §1/§2).

`resolve_role_user` and `get_stakeholders` are a binding contract: the (concurrently-built)
Submittal Workflow package resolves a workflow step's `reviewer_role` through
`resolve_role_user()`, so neither signature may change. Both degrade gracefully to `None`/`[]`
when a project has no `EGC Project Profile` row yet — that is a normal state, not an error,
since a fresh install seeds zero roles/modalities/manufacturers and a project may never get a
Profile at all.
"""

from __future__ import annotations

import frappe

#: Roles surfaced in the Hub header's `profile.key_stakeholders` (ARCHITECTURE_V2.md §4).
#: Names match the seed list documented in ARCHITECTURE_V2.md §2 — kept here, not in
#: `constants.py` (lead-owned), since this is Project Information's own read-side concern.
KEY_STAKEHOLDER_ROLES = ("EGC Project Manager", "EGC Site Manager", "Client", "Consultant", "OEM")


def resolve_role_user(project: str, role_name: str) -> str | None:
	"""The `user` of the project's stakeholder row for `role_name`, or None.

	None covers three distinct cases uniformly, by design: no Profile row exists yet, the role
	isn't represented among this project's stakeholders, or it is but the stakeholder is a pure
	external party with no Frappe login (ARCHITECTURE_V2.md §2). A caller that needs to tell
	these apart should use `get_stakeholders` directly.
	"""
	if not project or not role_name:
		return None

	rows = frappe.get_all(
		"EGC Project Stakeholder",
		filters={"parent": project, "parenttype": "EGC Project Profile", "role": role_name},
		fields=["user"],
		order_by="is_primary desc, idx asc",
		limit=1,
	)
	return rows[0].user or None if rows else None


def get_stakeholders(project: str) -> list[dict]:
	"""Every stakeholder row for `project`, or `[]` if it has no Profile yet."""
	if not project:
		return []

	return frappe.get_all(
		"EGC Project Stakeholder",
		filters={"parent": project, "parenttype": "EGC Project Profile"},
		fields=["role", "party_name", "organization", "user", "contact", "email", "phone", "is_primary"],
		order_by="idx asc",
	)
