# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for the email side of notifications.py — send_ball_in_court_email/
send_directory_welcome_email. `frappe.flags.mute_emails` is set for the whole class so
`frappe.sendmail(..., now=True)` queues into Email Queue without attempting a real SMTP
connection through the site's actual no-reply@egc-me.com account.
"""

import frappe
from frappe.tests import IntegrationTestCase

from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import notifications


def _make_company():
	return frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]


def _make_project(company):
	doc = frappe.get_doc(
		{"doctype": "Project", "project_name": f"EGC-NotifyEmail-Test-{frappe.generate_hash(length=8)}", "company": company}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


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


def _queued_recipients(email_queue_name):
	return frappe.get_all("Email Queue Recipient", filters={"parent": email_queue_name}, pluck="recipient")


class TestNotificationsEmail(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.flags.mute_emails = True

	@classmethod
	def tearDownClass(cls):
		frappe.flags.mute_emails = False
		super().tearDownClass()

	def setUp(self):
		self.project = _make_project(_make_company())

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_send_ball_in_court_email_queues_to_the_reviewer(self):
		user = _get_or_create_user("egc-notify-reviewer@example.com")
		submission = frappe.get_doc(
			{
				"doctype": "EGC Submittal Revision",
				"submittal": self._make_submittal(),
				"revision_label": "Rev 00",
				"project": self.project,
			}
		)
		submission.insert(ignore_permissions=True)

		before = frappe.db.count("Email Queue")
		notifications.send_ball_in_court_email(user, submission.name)
		after = frappe.db.count("Email Queue")
		self.assertEqual(after, before + 1)

		latest = frappe.get_all("Email Queue", order_by="creation desc", limit=1, fields=["name"])[0].name
		self.assertIn(user, _queued_recipients(latest))
		subject = frappe.db.get_value("Email Queue", latest, "message")
		self.assertIn("Rev 00", subject)

	def test_send_ball_in_court_email_skips_administrator(self):
		before = frappe.db.count("Email Queue")
		notifications.send_ball_in_court_email("Administrator", "does-not-matter")
		self.assertEqual(frappe.db.count("Email Queue"), before)

	def test_send_directory_welcome_email_queues_to_the_new_user(self):
		user = _get_or_create_user("egc-notify-welcome@example.com")

		before = frappe.db.count("Email Queue")
		notifications.send_directory_welcome_email(user, self.project)
		after = frappe.db.count("Email Queue")
		self.assertEqual(after, before + 1)

		latest = frappe.get_all("Email Queue", order_by="creation desc", limit=1, fields=["name"])[0].name
		self.assertIn(user, _queued_recipients(latest))

	def _make_submittal(self):
		if not frappe.db.exists("EGC Submittal Type", "EGC-NotifyEmail-Type"):
			frappe.get_doc(
				{"doctype": "EGC Submittal Type", "submittal_type_name": "EGC-NotifyEmail-Type"}
			).insert(ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "EGC Submittal",
				"project": self.project,
				"submittal_number": f"SUB-NOTIFY-{frappe.generate_hash(length=6)}",
				"title": "Notify Email Test Submittal",
				"submittal_type": "EGC-NotifyEmail-Type",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
