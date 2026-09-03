# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for egc_projects.egc_projects.comments — the generic Comment(+Communication) thread any
EGC record's Hub detail page reads/writes through. Exercised against the core `Project` doctype
directly rather than an EGC-specific one: the module is doctype-agnostic by design (its own
docstring), and every assertion here is about the read-permission gate and the
edit/delete-ownership rules, not about EGC Submittal/Document/Activity semantics.
"""

import frappe
from frappe.tests import IntegrationTestCase

from egc_projects.egc_projects import comments


def _make_company():
	return frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]


def _make_project():
	doc = frappe.get_doc(
		{"doctype": "Project", "project_name": f"EGC-Comments-Test-{frappe.generate_hash(length=8)}", "company": _make_company()}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_user(email, roles=()):
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


class TestComments(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.project = _make_project()

	def tearDown(self):
		frappe.set_user("Administrator")

	# -- get_comments / add_comment (pre-existing, previously untested directly) -----------------

	def test_add_comment_then_get_comments_round_trips(self):
		result = comments.add_comment("Project", self.project, "Hello there")
		self.assertTrue(result["name"])
		self.assertEqual(result["content"], "Hello there")

		rows = comments.get_comments("Project", self.project)
		self.assertEqual([r.name for r in rows], [result["name"]])

	def test_add_comment_rejects_blank_content(self):
		self.assertRaises(frappe.ValidationError, comments.add_comment, "Project", self.project, "   ")

	def test_get_comments_denies_a_user_with_no_read_access(self):
		user = _make_user("comments-test-noaccess@example.com")
		frappe.set_user(user)
		self.assertRaises(frappe.PermissionError, comments.get_comments, "Project", self.project)

	# -- get_activity -------------------------------------------------------------------------------

	def test_get_activity_returns_comments_and_communications_together(self):
		comments.add_comment("Project", self.project, "A real comment")
		frappe.get_doc(
			{
				"doctype": "Communication",
				"communication_type": "Communication",
				"communication_medium": "Email",
				"reference_doctype": "Project",
				"reference_name": self.project,
				"sent_or_received": "Sent",
				"subject": "Test email",
				"content": "Body",
			}
		).insert(ignore_permissions=True)

		result = comments.get_activity("Project", self.project)
		self.assertEqual(len(result["comments"]), 1)
		self.assertEqual(result["comments"][0]["content"], "A real comment")
		self.assertEqual(len(result["communications"]), 1)
		self.assertEqual(result["communications"][0]["subject"], "Test email")

	def test_get_activity_denies_a_user_with_no_read_access(self):
		user = _make_user("comments-test-noaccess2@example.com")
		frappe.set_user(user)
		self.assertRaises(frappe.PermissionError, comments.get_activity, "Project", self.project)

	# -- update_comment -------------------------------------------------------------------------------

	def test_update_comment_by_owner_succeeds(self):
		author = _make_user("comments-test-author@example.com", ["Projects User"])
		frappe.get_doc({"doctype": "User Permission", "user": author, "allow": "Project", "for_value": self.project}).insert(
			ignore_permissions=True
		)
		frappe.set_user(author)
		created = comments.add_comment("Project", self.project, "Original")

		result = comments.update_comment("Project", self.project, created["name"], "Edited")
		self.assertEqual(result["content"], "Edited")

	def test_update_comment_by_a_different_user_is_denied(self):
		created = comments.add_comment("Project", self.project, "Original")
		# Holds real read access (Projects User, no scoping User Permission — sees every project)
		# so this exercises the ownership rule itself, not just the outer read gate.
		other = _make_user("comments-test-other@example.com", ["Projects User"])
		frappe.set_user(other)
		self.assertRaises(frappe.PermissionError, comments.update_comment, "Project", self.project, created["name"], "Hacked")

	def test_update_comment_rejects_a_comment_from_another_reference(self):
		other_project = _make_project()
		created = comments.add_comment("Project", other_project, "Belongs elsewhere")
		self.assertRaises(frappe.PermissionError, comments.update_comment, "Project", self.project, created["name"], "Edited")

	# -- delete_comment -------------------------------------------------------------------------------

	def test_delete_comment_by_owner_succeeds(self):
		created = comments.add_comment("Project", self.project, "To be deleted")
		comments.delete_comment("Project", self.project, created["name"])
		self.assertFalse(frappe.db.exists("Comment", created["name"]))

	def test_delete_comment_by_system_manager_who_is_not_the_owner_succeeds(self):
		author = _make_user("comments-test-author2@example.com", ["Projects User"])
		frappe.set_user(author)
		created = comments.add_comment("Project", self.project, "Someone else's comment")

		# System Manager alone doesn't carry Project doctype-level read in this bench (see
		# restrict_financial_field_permlevel/install.py's own Project permission customization)
		# — Projects User is what actually satisfies the read gate; System Manager is what's
		# actually under test (delete allowed despite not being the comment's own author).
		manager = _make_user("comments-test-manager@example.com", ["System Manager", "Projects User"])
		frappe.set_user(manager)
		comments.delete_comment("Project", self.project, created["name"])
		self.assertFalse(frappe.db.exists("Comment", created["name"]))

	def test_delete_comment_by_an_unrelated_user_is_denied(self):
		created = comments.add_comment("Project", self.project, "Protected")
		# Real read access (Projects User, unscoped), no System Manager role and not the
		# author — exercises the ownership/System-Manager rule, not just the read gate.
		other = _make_user("comments-test-unrelated@example.com", ["Projects User"])
		frappe.set_user(other)
		self.assertRaises(frappe.PermissionError, comments.delete_comment, "Project", self.project, created["name"])
		self.assertTrue(frappe.db.exists("Comment", created["name"]))
