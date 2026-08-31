# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for the Hub's Directory tab API (api/directory.py): surfacing `EGC Project Stakeholder`
rows with Portal Access state, and granting/revoking that access — the same read-only
`EGC External Viewer` role + `User Permission`-scoped-to-one-Project pattern already proven in
test_external_viewer.py, now reachable from the Hub.
"""

import frappe
from frappe.tests import IntegrationTestCase

from egc_projects.api import directory
from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import project_profile


def _make_company():
	return frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]


def _make_project(company):
	doc = frappe.get_doc(
		{"doctype": "Project", "project_name": f"EGC-DirHub-Test-{frappe.generate_hash(length=8)}", "company": company}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_role(role_name, is_egc_internal=0):
	if frappe.db.exists("EGC Stakeholder Role", role_name):
		return role_name
	frappe.get_doc(
		{"doctype": "EGC Stakeholder Role", "role_name": role_name, "is_egc_internal": is_egc_internal}
	).insert(ignore_permissions=True)
	return role_name


def _get_or_create_user(email, roles=()):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		)
		user.insert(ignore_permissions=True)
	if roles:
		user.add_roles(*roles)
	return user.name


class TestDirectoryHub(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		# grant_portal_access sends a welcome email on first grant (notifications.py) — muted so
		# these tests never attempt a real send through the site's actual no-reply@egc-me.com
		# account.
		frappe.flags.mute_emails = True
		cls.manager_user = _get_or_create_user("egc-dh-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER])
		cls.role_internal = _get_or_create_role("EGC-DH-Internal Role", is_egc_internal=1)
		cls.role_external = _get_or_create_role("EGC-DH-External Role", is_egc_internal=0)

	@classmethod
	def tearDownClass(cls):
		frappe.flags.mute_emails = False
		super().tearDownClass()

	def setUp(self):
		self.project = _make_project(_make_company())

	def tearDown(self):
		frappe.set_user("Administrator")

	def _add_stakeholder(self, role, party_name, person=None):
		frappe.set_user(self.manager_user)
		row_name = project_profile.add_stakeholder(
			self.project, {"role": role, "party_name": party_name, "person": person}
		)
		frappe.set_user("Administrator")
		return row_name

	# -- get_directory ---------------------------------------------------------------------------

	def test_get_directory_empty_on_fresh_project(self):
		frappe.set_user(self.manager_user)
		self.assertEqual(directory.get_directory(self.project), [])

	def test_get_directory_flags_internal_and_external(self):
		self._add_stakeholder(self.role_internal, "Internal Person")
		self._add_stakeholder(self.role_external, "External Person")

		frappe.set_user(self.manager_user)
		rows = directory.get_directory(self.project)
		by_name = {row["party_name"]: row for row in rows}
		self.assertTrue(by_name["Internal Person"]["is_egc_internal"])
		self.assertFalse(by_name["External Person"]["is_egc_internal"])

	def test_get_directory_reports_no_portal_access_without_a_user(self):
		self._add_stakeholder(self.role_internal, "No Login Yet")

		frappe.set_user(self.manager_user)
		rows = directory.get_directory(self.project)
		self.assertFalse(rows[0]["has_portal_access"])
		self.assertEqual(rows[0]["portal_roles"], [])

	def test_get_directory_resolves_organization_display_name(self):
		# `row.organization` is a Customer Link value (a naming-series code, e.g. "CUST-2026-
		# 00001") — unlike the old EGC Organization, it's never presentable on its own. Regression
		# coverage for the Directory tab briefly showing that raw code instead of a name.
		customer_name = "EGC-DH-Org-Display-Name"
		customer = frappe.get_doc({"doctype": "Customer", "customer_name": customer_name}).insert(
			ignore_permissions=True
		)
		frappe.set_user(self.manager_user)
		project_profile.add_stakeholder(
			self.project, {"role": self.role_external, "party_name": "Org Display Target", "organization": customer.name}
		)

		rows = directory.get_directory(self.project)
		self.assertEqual(rows[0]["organization"], customer.name)
		self.assertEqual(rows[0]["organization_name"], customer_name)

	# -- grant_portal_access -----------------------------------------------------------------------

	def test_grant_portal_access_creates_user_and_scopes_project(self):
		row_name = self._add_stakeholder(self.role_external, "Client Rep")

		frappe.set_user(self.manager_user)
		result = directory.grant_portal_access(
			self.project, row_name, c.ROLE_EXTERNAL_VIEWER, email="egc-dh-newclient@example.com"
		)
		user = result["user"]

		self.assertTrue(frappe.db.exists("User", user))
		self.assertIn(c.ROLE_EXTERNAL_VIEWER, frappe.get_roles(user))
		self.assertTrue(
			frappe.db.exists("User Permission", {"user": user, "allow": "Project", "for_value": self.project})
		)
		# Mirrored back onto the stakeholder row.
		self.assertEqual(frappe.db.get_value("EGC Project Stakeholder", row_name, "person"), user)

		rows = directory.get_directory(self.project)
		self.assertTrue(rows[0]["has_portal_access"])
		self.assertIn(c.ROLE_EXTERNAL_VIEWER, rows[0]["portal_roles"])

	def test_grant_portal_access_reuses_existing_user_for_that_email(self):
		existing = _get_or_create_user("egc-dh-existing@example.com")
		row_name = self._add_stakeholder(self.role_internal, "Reuses Existing")

		frappe.set_user(self.manager_user)
		result = directory.grant_portal_access(
			self.project, row_name, c.ROLE_PROJECT_ENGINEER, email="egc-dh-existing@example.com"
		)
		self.assertEqual(result["user"], existing)

	def test_grant_portal_access_reuses_the_row_s_own_person_when_already_a_user(self):
		# `person` links directly to a User now — a stakeholder row that already has one set
		# (added via the normal "pick from the Directory" path, not a fresh email) must have
		# THAT user granted access, never a new one created alongside it.
		org_name = "EGC-DH-Test-Org"
		org = frappe.db.get_value("Customer", {"customer_name": org_name})
		if not org:
			org = frappe.get_doc({"doctype": "Customer", "customer_name": org_name}).insert(ignore_permissions=True).name
		person = frappe.get_doc(
			{
				"doctype": "User",
				"email": "egc-dh-personlinked@example.com",
				"first_name": "Directory Linked Person",
				"send_welcome_email": 0,
			}
		)
		person.insert(ignore_permissions=True)
		customer = frappe.get_doc("Customer", org)
		customer.append("portal_users", {"user": person.name})
		customer.save(ignore_permissions=True)

		frappe.set_user(self.manager_user)
		row_name = project_profile.add_stakeholder(self.project, {"role": self.role_external, "person": person.name})
		frappe.set_user(self.manager_user)

		result = directory.grant_portal_access(self.project, row_name, c.ROLE_EXTERNAL_VIEWER)

		self.assertEqual(result["user"], person.name)

	def test_grant_portal_access_without_email_and_no_existing_user_raises(self):
		row_name = self._add_stakeholder(self.role_external, "No Email Given")

		frappe.set_user(self.manager_user)
		with self.assertRaises(frappe.ValidationError):
			directory.grant_portal_access(self.project, row_name, c.ROLE_EXTERNAL_VIEWER)

	def test_grant_portal_access_rejects_ungrantable_role(self):
		row_name = self._add_stakeholder(self.role_external, "Bad Role Target")

		frappe.set_user(self.manager_user)
		with self.assertRaises(frappe.ValidationError):
			directory.grant_portal_access(self.project, row_name, "System Manager", email="egc-dh-x@example.com")

	def test_grant_portal_access_rejects_row_from_another_project(self):
		other_project = _make_project(_make_company())
		frappe.set_user(self.manager_user)
		other_row = project_profile.add_stakeholder(other_project, {"role": self.role_external, "party_name": "Elsewhere"})

		with self.assertRaises(frappe.PermissionError):
			directory.grant_portal_access(self.project, other_row, c.ROLE_EXTERNAL_VIEWER, email="egc-dh-y@example.com")

	def test_grant_portal_access_sends_one_welcome_email_on_first_grant(self):
		row_name = self._add_stakeholder(self.role_external, "Welcome Email Target")
		frappe.set_user(self.manager_user)

		before = frappe.db.count("Email Queue")
		directory.grant_portal_access(
			self.project, row_name, c.ROLE_EXTERNAL_VIEWER, email="egc-dh-welcome@example.com"
		)
		self.assertEqual(frappe.db.count("Email Queue"), before + 1)

	def test_grant_portal_access_does_not_resend_while_access_is_still_active(self):
		# Granting a SECOND role to someone who already has active access (no revoke in between)
		# is not a fresh onboarding — is_first_grant is keyed on current User Permission
		# existence, so this must not queue a second welcome email.
		row_name = self._add_stakeholder(self.role_external, "No Duplicate Welcome Target")
		frappe.set_user(self.manager_user)
		directory.grant_portal_access(
			self.project, row_name, c.ROLE_EXTERNAL_VIEWER, email="egc-dh-noresend@example.com"
		)

		before = frappe.db.count("Email Queue")
		directory.grant_portal_access(self.project, row_name, c.ROLE_PROJECT_VIEWER, email="egc-dh-noresend@example.com")
		self.assertEqual(frappe.db.count("Email Queue"), before)

	# -- revoke_portal_access ----------------------------------------------------------------------

	def test_revoke_portal_access_removes_user_permission_but_keeps_user(self):
		row_name = self._add_stakeholder(self.role_external, "Revoke Me")
		frappe.set_user(self.manager_user)
		result = directory.grant_portal_access(
			self.project, row_name, c.ROLE_EXTERNAL_VIEWER, email="egc-dh-revoke@example.com"
		)
		user = result["user"]

		directory.revoke_portal_access(self.project, user)

		self.assertFalse(
			frappe.db.exists("User Permission", {"user": user, "allow": "Project", "for_value": self.project})
		)
		self.assertTrue(frappe.db.exists("User", user))

	def test_revoke_portal_access_strips_egc_roles_when_it_was_the_last_project_scope(self):
		# Regression for a real privilege-escalation bug: Frappe's own `has_user_permission`
		# returns True unconditionally for a user with ZERO `User Permission` rows for a doctype
		# (confirmed directly against frappe/permissions.py), so leaving an EGC role behind after
		# removing someone's only Project scope would silently upgrade them from "sees one
		# project" to "sees every project" the moment revoke runs. The role must go with it.
		row_name = self._add_stakeholder(self.role_external, "Last Scope Revoke")
		frappe.set_user(self.manager_user)
		result = directory.grant_portal_access(
			self.project, row_name, c.ROLE_EXTERNAL_VIEWER, email="egc-dh-lastscope@example.com"
		)
		user = result["user"]
		self.assertIn(c.ROLE_EXTERNAL_VIEWER, frappe.get_roles(user))

		directory.revoke_portal_access(self.project, user)

		self.assertNotIn(c.ROLE_EXTERNAL_VIEWER, frappe.get_roles(user))
		self.assertTrue(frappe.db.exists("User", user))

	def test_revoke_portal_access_keeps_role_when_user_still_scoped_to_another_project(self):
		# The opposite case must also hold: revoking ONE project's access must not strip a role
		# the user still legitimately needs for a DIFFERENT project they remain scoped to.
		from frappe.permissions import add_user_permission

		other_project = _make_project(_make_company())
		row_name = self._add_stakeholder(self.role_external, "Multi Project Person")
		frappe.set_user(self.manager_user)
		result = directory.grant_portal_access(
			self.project, row_name, c.ROLE_EXTERNAL_VIEWER, email="egc-dh-multiproj@example.com"
		)
		user = result["user"]
		add_user_permission("Project", other_project, user, ignore_permissions=True)

		directory.revoke_portal_access(self.project, user)

		self.assertIn(c.ROLE_EXTERNAL_VIEWER, frappe.get_roles(user))
		self.assertTrue(
			frappe.db.exists("User Permission", {"user": user, "allow": "Project", "for_value": other_project})
		)

	# -- update_stakeholder_role -------------------------------------------------------------------

	def test_update_stakeholder_role_changes_the_row(self):
		row_name = self._add_stakeholder(self.role_internal, "Role Change Target")

		frappe.set_user(self.manager_user)
		directory.update_stakeholder_role(self.project, row_name, self.role_external)

		self.assertEqual(frappe.db.get_value("EGC Project Stakeholder", row_name, "role"), self.role_external)

	# -- permission gating (project isolation — the real boundary this app enforces; "Projects
	# User", required just to open the Hub at all, already grants generic write on core Project,
	# so a same-project role check would pass for any Hub user regardless of role — see
	# test_project_info.py's own test_edit_profile_matches_project_write_permission comment) ----

	def test_endpoints_reject_a_user_with_no_access_to_this_project(self):
		row_name = self._add_stakeholder(self.role_external, "Isolation Target")
		other_project = _make_project(_make_company())
		fenced_user = _get_or_create_user("egc-dh-fenced@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER])
		frappe.get_doc(
			{"doctype": "User Permission", "user": fenced_user, "allow": "Project", "for_value": other_project}
		).insert(ignore_permissions=True)

		frappe.set_user(fenced_user)
		with self.assertRaises(frappe.PermissionError):
			directory.get_directory(self.project)
		with self.assertRaises(frappe.PermissionError):
			directory.grant_portal_access(self.project, row_name, c.ROLE_EXTERNAL_VIEWER, email="egc-dh-z@example.com")
		with self.assertRaises(frappe.PermissionError):
			directory.update_stakeholder_role(self.project, row_name, self.role_internal)
