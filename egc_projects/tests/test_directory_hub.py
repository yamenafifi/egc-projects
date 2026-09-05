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
from egc_projects.egc_projects import project_profile, submittal_control
from egc_projects.tests.test_submittal_workflow import (
	_get_or_create_discipline,
	_get_or_create_document_type,
	_get_or_create_stakeholder_role,
	_get_or_create_submittal_type,
)


def _make_company():
	return frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]


def _make_project(company):
	doc = frappe.get_doc(
		{"doctype": "Project", "project_name": f"EGC-DirHub-Test-{frappe.generate_hash(length=8)}", "company": company}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_role(role_name, is_egc_internal=0, default_roles=()):
	if frappe.db.exists("EGC Stakeholder Role", role_name):
		return role_name
	frappe.get_doc(
		{
			"doctype": "EGC Stakeholder Role",
			"role_name": role_name,
			"is_egc_internal": is_egc_internal,
			"default_roles": [{"role": role} for role in default_roles],
		}
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
		cls.role_internal = _get_or_create_role(
			"EGC-DH-Internal Role", is_egc_internal=1, default_roles=(c.ROLE_PROJECT_VIEWER,)
		)
		cls.role_external = _get_or_create_role(
			"EGC-DH-External Role", is_egc_internal=0, default_roles=(c.ROLE_EXTERNAL_VIEWER,)
		)
		#: A Stakeholder Role with NO default_roles template — for asserting grant_portal_access
		#: applies nothing beyond project visibility when there's nothing to apply.
		cls.role_no_template = _get_or_create_role("EGC-DH-No-Template Role", is_egc_internal=0)

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
		result = directory.grant_portal_access(self.project, row_name, email="egc-dh-newclient@example.com")
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
		result = directory.grant_portal_access(self.project, row_name, email="egc-dh-existing@example.com")
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

		result = directory.grant_portal_access(self.project, row_name)

		self.assertEqual(result["user"], person.name)

	def test_grant_portal_access_without_email_and_no_existing_user_raises(self):
		row_name = self._add_stakeholder(self.role_external, "No Email Given")

		frappe.set_user(self.manager_user)
		with self.assertRaises(frappe.ValidationError):
			directory.grant_portal_access(self.project, row_name)

	def test_grant_portal_access_applies_nothing_when_stakeholder_role_has_no_template(self):
		# A Stakeholder Role with an empty default_roles template (most real-world titles —
		# Architect, Client, Site Contact) grants project visibility only, no extra Frappe Role.
		row_name = self._add_stakeholder(self.role_no_template, "No Template Target")

		frappe.set_user(self.manager_user)
		result = directory.grant_portal_access(self.project, row_name, email="egc-dh-notemplate@example.com")
		user = result["user"]

		self.assertTrue(
			frappe.db.exists("User Permission", {"user": user, "allow": "Project", "for_value": self.project})
		)
		self.assertEqual(set(frappe.get_roles(user)) & set(c.EGC_ROLES), set())

	def test_grant_portal_access_never_touches_an_unrelated_role(self):
		# Direct user instruction: applying a Stakeholder Role's template must be additive only —
		# an unrelated role (e.g. Accounts User) a person already holds must never be stripped.
		row_name = self._add_stakeholder(self.role_external, "Keeps Accounting Role")
		email = "egc-dh-accounting@example.com"
		_get_or_create_user(email, ["Accounts User"])

		frappe.set_user(self.manager_user)
		result = directory.grant_portal_access(self.project, row_name, email=email)

		self.assertIn("Accounts User", frappe.get_roles(result["user"]))
		self.assertIn(c.ROLE_EXTERNAL_VIEWER, frappe.get_roles(result["user"]))

	def test_grant_portal_access_rejects_row_from_another_project(self):
		other_project = _make_project(_make_company())
		frappe.set_user(self.manager_user)
		other_row = project_profile.add_stakeholder(other_project, {"role": self.role_external, "party_name": "Elsewhere"})

		with self.assertRaises(frappe.PermissionError):
			directory.grant_portal_access(self.project, other_row, email="egc-dh-y@example.com")

	def test_grant_portal_access_sends_one_welcome_email_on_first_grant(self):
		row_name = self._add_stakeholder(self.role_external, "Welcome Email Target")
		frappe.set_user(self.manager_user)

		before = frappe.db.count("Email Queue")
		directory.grant_portal_access(self.project, row_name, email="egc-dh-welcome@example.com")
		self.assertEqual(frappe.db.count("Email Queue"), before + 1)

	def test_grant_portal_access_does_not_resend_while_access_is_still_active(self):
		# Granting access a SECOND time to someone who already has active access (no revoke in
		# between) is not a fresh onboarding — is_first_grant is keyed on current User Permission
		# existence, so this must not queue a second welcome email.
		row_name = self._add_stakeholder(self.role_external, "No Duplicate Welcome Target")
		frappe.set_user(self.manager_user)
		directory.grant_portal_access(self.project, row_name, email="egc-dh-noresend@example.com")

		before = frappe.db.count("Email Queue")
		directory.grant_portal_access(self.project, row_name)
		self.assertEqual(frappe.db.count("Email Queue"), before)

	def test_grant_portal_access_skips_user_permission_for_a_bypass_role_holder(self):
		# The actual regression this app hit: an admin (System Manager) granted Directory access
		# must NEVER end up with a scoping User Permission — Frappe's own User Permission
		# enforcement has no role-based bypass, so even one such row would cost them visibility of
		# every OTHER project regardless of their roles.
		admin = _get_or_create_user("egc-dh-admin@example.com", ["System Manager"])
		row_name = self._add_stakeholder(self.role_external, "Admin Target", person=admin)

		frappe.set_user(self.manager_user)
		directory.grant_portal_access(self.project, row_name)

		self.assertFalse(
			frappe.db.exists("User Permission", {"user": admin, "allow": "Project", "for_value": self.project})
		)
		rows = directory.get_directory(self.project)
		row = next(r for r in rows if r["name"] == row_name)
		self.assertTrue(row["is_admin_bypass"])
		self.assertTrue(row["has_portal_access"])

	def test_grant_portal_access_skips_user_permission_for_an_internal_stakeholder(self):
		# The second instance of the exact same regression: an internal EGC stakeholder (Document
		# Controller, Project Engineer, ...) is not a bypass-role holder, but their Stakeholder
		# Role already grants a real EGC role meant to work across every project they're on.
		# Scoping them with a Project User Permission here would silently narrow their access on
		# every OTHER doctype that links to Project (Purchase Order, Purchase Invoice,
		# Timesheet, ...), system-wide, not just this app — confirmed live in production.
		internal_user = _get_or_create_user("egc-dh-internal@example.com")
		row_name = self._add_stakeholder(self.role_internal, "Internal Target", person=internal_user)

		frappe.set_user(self.manager_user)
		directory.grant_portal_access(self.project, row_name)

		self.assertFalse(
			frappe.db.exists(
				"User Permission", {"user": internal_user, "allow": "Project", "for_value": self.project}
			)
		)
		self.assertIn(c.ROLE_PROJECT_VIEWER, frappe.get_roles(internal_user))
		rows = directory.get_directory(self.project)
		row = next(r for r in rows if r["name"] == row_name)
		self.assertFalse(row["is_admin_bypass"])
		self.assertTrue(row["is_internal_unscoped"])
		self.assertTrue(row["has_portal_access"])

	# -- revoke_portal_access ----------------------------------------------------------------------

	def test_revoke_portal_access_removes_user_permission_but_keeps_user(self):
		row_name = self._add_stakeholder(self.role_external, "Revoke Me")
		frappe.set_user(self.manager_user)
		result = directory.grant_portal_access(self.project, row_name, email="egc-dh-revoke@example.com")
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
		result = directory.grant_portal_access(self.project, row_name, email="egc-dh-lastscope@example.com")
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
		result = directory.grant_portal_access(self.project, row_name, email="egc-dh-multiproj@example.com")
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
			directory.grant_portal_access(self.project, row_name, email="egc-dh-z@example.com")
		with self.assertRaises(frappe.PermissionError):
			directory.update_stakeholder_role(self.project, row_name, self.role_internal)


class TestDirectoryPersonProfile(IntegrationTestCase):
	"""Tests for get_person_profile (the Hub's Directory Person page — replaces routing a row
	click to the raw native User form) and project_profile.update_stakeholder (that page's own
	fuller edit, everything add_stakeholder accepts except `person`). Builds real Submittal/
	Document/Assignment fixtures — reusing test_submittal_workflow.py's own free helper
	functions, same precedent test_submittal_forwarding.py already sets — to prove the "what
	they've done on this project" sections aren't just empty-state placeholders."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
		cls.document_type = _get_or_create_document_type()
		cls.discipline = _get_or_create_discipline()
		cls.submittal_type = _get_or_create_submittal_type()
		cls.role_engineer = _get_or_create_stakeholder_role("EGC-DPP-Engineer Role", is_egc_internal=1)
		cls.manager_user = _get_or_create_user("egc-dpp-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER])
		cls.reviewer = _get_or_create_user("egc-dpp-reviewer@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER])

	def setUp(self):
		self.project = _make_project(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _add_stakeholder(self, party_name, person=None):
		frappe.set_user(self.manager_user)
		row_name = project_profile.add_stakeholder(
			self.project, {"role": self.role_engineer, "party_name": party_name, "person": person}
		)
		frappe.set_user("Administrator")
		return row_name

	def _make_document(self, document_number, originator_person=None):
		doc = frappe.get_doc(
			{
				"doctype": "EGC Project Document",
				"project": self.project,
				"document_number": document_number,
				"title": document_number,
				"document_type": self.document_type,
				"discipline": self.discipline,
				"originator_person": originator_person,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_private_file(self):
		f = frappe.get_doc(
			{"doctype": "File", "file_name": f"{frappe.generate_hash(length=6)}.txt", "is_private": 1, "content": "x"}
		)
		f.insert(ignore_permissions=True)
		return f.file_url

	def _make_responded_review_step(self, reviewer_user):
		"""A real Submittal -> Revision -> Review Step chain, responded, so
		_get_review_activity has something genuine to join across three doctypes for."""
		document = self._make_document(f"DOC-DPP-{frappe.generate_hash(length=6)}")
		revision = frappe.get_doc(
			{
				"doctype": "EGC Project Document Revision",
				"document": document.name,
				"revision": "00",
				"file": self._make_private_file(),
				"revision_date": frappe.utils.today(),
			}
		)
		revision.insert(ignore_permissions=True)
		revision.submit()

		submittal = frappe.get_doc(
			{
				"doctype": "EGC Submittal",
				"project": self.project,
				"submittal_number": f"SUB-DPP-{frappe.generate_hash(length=6)}",
				"title": "Test Submittal",
				"submittal_type": self.submittal_type,
				"discipline": self.discipline,
			}
		)
		submittal.insert(ignore_permissions=True)

		submission = frappe.get_doc(
			{
				"doctype": "EGC Submittal Revision",
				"submittal": submittal.name,
				"revision_label": "00",
				"date_submitted": frappe.utils.today(),
			}
		)
		submission.append("documents", {"document_revision": revision.name})
		submission.insert(ignore_permissions=True)

		step = frappe.get_doc(
			{
				"doctype": "EGC Submittal Review Step",
				"submittal_revision": submission.name,
				"sequence": 0,
				"reviewer_user": reviewer_user,
				"reviewer_label": reviewer_user,
				"is_required": 1,
			}
		)
		step.insert(ignore_permissions=True)
		submission.submit()

		# Not a hand-set status/response — that's blocked outright ("Status is controlled by the
		# review workflow and cannot be set directly", confirmed live running this test before this
		# fix), by design (this app's own no-fake-review principle). Goes through the real engine,
		# same as every actual response in this app does; Administrator carries the "internal
		# override" record_step_response's own docstring mentions, no need to switch session user.
		submittal_control.record_step_response(step.name, c.RESPONSE_APPROVED, remarks="Looks good")
		step.reload()
		return submittal, step

	# -- get_person_profile -------------------------------------------------------------------------

	def test_get_person_profile_for_a_login_less_party_has_empty_activity(self):
		row_name = self._add_stakeholder("No Login Yet")

		frappe.set_user(self.manager_user)
		result = directory.get_person_profile(self.project, row_name)

		self.assertEqual(result["row"]["party_name"], "No Login Yet")
		self.assertIsNone(result["row"]["person"])
		self.assertEqual(result["activity"], {"reviews": [], "documents": [], "assignments": []})

	def test_get_person_profile_includes_review_documents_and_assignments(self):
		row_name = self._add_stakeholder("Real Reviewer", person=self.reviewer)
		submittal, step = self._make_responded_review_step(self.reviewer)
		document = self._make_document(f"DOC-DPP-ORIG-{frappe.generate_hash(length=6)}", originator_person=self.reviewer)
		frappe.get_doc(
			{
				"doctype": "EGC Assignment",
				"parent_doctype": "EGC Submittal",
				"parent_name": submittal.name,
				"project": self.project,
				"assignment_role": "Reviewer",
				"person": self.reviewer,
			}
		).insert(ignore_permissions=True)

		frappe.set_user(self.manager_user)
		result = directory.get_person_profile(self.project, row_name)

		self.assertEqual(len(result["activity"]["reviews"]), 1)
		review = result["activity"]["reviews"][0]
		self.assertEqual(review["response"], c.RESPONSE_APPROVED)
		self.assertEqual(review["submittal"], submittal.name)
		self.assertEqual(review["submittal_number"], submittal.submittal_number)

		self.assertEqual(len(result["activity"]["documents"]), 1)
		self.assertEqual(result["activity"]["documents"][0]["name"], document.name)

		self.assertEqual(len(result["activity"]["assignments"]), 1)
		assignment = result["activity"]["assignments"][0]
		self.assertEqual(assignment["parent_name"], submittal.name)
		self.assertEqual(assignment["parent_title"], submittal.title)

	def test_get_person_profile_denies_a_user_with_no_project_access(self):
		row_name = self._add_stakeholder("Fenced Target")
		other_project = _make_project(self.company)
		fenced_user = _get_or_create_user("egc-dpp-fenced@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER])
		frappe.get_doc(
			{"doctype": "User Permission", "user": fenced_user, "allow": "Project", "for_value": other_project}
		).insert(ignore_permissions=True)

		frappe.set_user(fenced_user)
		self.assertRaises(frappe.PermissionError, directory.get_person_profile, self.project, row_name)

	def test_get_person_profile_rejects_a_row_from_another_project(self):
		row_name = self._add_stakeholder("Wrong Project Target")
		other_project = _make_project(self.company)

		frappe.set_user(self.manager_user)
		self.assertRaises(frappe.PermissionError, directory.get_person_profile, other_project, row_name)

	# -- project_profile.update_stakeholder ----------------------------------------------------------

	def test_update_stakeholder_edits_fields_and_resyncs_role_on_change(self):
		# party_name/email are intentionally NOT independently editable once `person` is set —
		# EGCProjectStakeholder.fetch_from_person() (validate()) re-derives them from the linked
		# User on every save "so this row's own display fields always mirror the Directory record
		# rather than drifting into an independent copy" (that doctype's own docstring). Confirmed
		# live before writing this test: an attempted party_name/email edit here is silently
		# discarded, not applied then overwritten by something else — role and is_primary are the
		# fields actually under this app's own control for a person-linked row.
		row_name = self._add_stakeholder("Edit Target", person=self.reviewer)
		new_role = _get_or_create_stakeholder_role("EGC-DPP-New Role", is_egc_internal=0)

		frappe.set_user(self.manager_user)
		project_profile.update_stakeholder(
			self.project, row_name, {"party_name": "Edited Name", "email": "edited@example.com", "role": new_role, "is_primary": 1}
		)

		updated = frappe.db.get_value(
			"EGC Project Stakeholder", row_name, ["party_name", "email", "role", "is_primary"], as_dict=True
		)
		self.assertEqual(updated.role, new_role)
		self.assertEqual(updated.is_primary, 1)
		self.assertEqual(updated.party_name, frappe.utils.get_fullname(self.reviewer))
		self.assertEqual(updated.email, self.reviewer)

	def test_update_stakeholder_edits_free_text_fields_for_a_login_less_party(self):
		# The mirror case: with no `person` to derive from, fetch_from_person() is a no-op
		# (`if not self.person: return`) — party_name/email/phone genuinely are this row's own
		# data for a one-off party, and update_stakeholder's edit actually sticks.
		row_name = self._add_stakeholder("Login-less Edit Target")

		frappe.set_user(self.manager_user)
		project_profile.update_stakeholder(
			self.project, row_name, {"party_name": "Edited Name", "email": "edited@example.com", "phone": "555-0100"}
		)

		updated = frappe.db.get_value(
			"EGC Project Stakeholder", row_name, ["party_name", "email", "phone"], as_dict=True
		)
		self.assertEqual(updated.party_name, "Edited Name")
		self.assertEqual(updated.email, "edited@example.com")
		self.assertEqual(updated.phone, "555-0100")

	def test_update_stakeholder_never_changes_person(self):
		row_name = self._add_stakeholder("Person Lock Target", person=self.reviewer)
		other_user = _get_or_create_user("egc-dpp-other@example.com", ["Projects User"])

		frappe.set_user(self.manager_user)
		project_profile.update_stakeholder(self.project, row_name, {"person": other_user, "is_primary": 1})

		updated = frappe.db.get_value("EGC Project Stakeholder", row_name, ["person", "is_primary"], as_dict=True)
		self.assertEqual(updated.person, self.reviewer)
		self.assertEqual(updated.is_primary, 1)

	def test_update_stakeholder_denies_a_user_with_no_write_access(self):
		row_name = self._add_stakeholder("Write-Denied Target")
		viewer_only = _get_or_create_user("egc-dpp-viewer@example.com", [])

		frappe.set_user(viewer_only)
		self.assertRaises(
			frappe.PermissionError, project_profile.update_stakeholder, self.project, row_name, {"party_name": "Hacked"}
		)
