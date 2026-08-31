# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for notifications.py — notify_submission_received/notify_response_recorded/
notify_new_revision/notify_activity_assigned/send_due_date_reminders/
send_activity_due_date_reminders. Previously only the email side (test_notifications_email.py)
had any coverage at all.

The event-triggered notifiers (submission received, response recorded, new revision, activity
assigned) all create a real Frappe ToDo via `_assign_task` (`frappe.desk.form.assign_to._add`),
mirroring `submittal_control.py`'s own ball-in-court `_assign_step` — a passive Notification Log
alone was not an actionable "task". `notify_activity_assigned` closes a gap that previously had
NOTHING at all: `assignments.add_assignment` never notified an Activity's own team before this.
`_add` is mocked rather than asserting a real ToDo row exists, matching how `_assign_step` itself
is exercised elsewhere in this app's test suite.

`send_due_date_reminders`/`send_activity_due_date_reminders` are a different, in-app-only
reminder ping via `enqueue_create_notification` (dispatched through `frappe.enqueue(...)` onto a
real Redis queue, not synchronous) — kept on `_notify`, covered by their own tests below.
"""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from egc_projects.egc_projects import notifications


def _get_or_create_user(email):
	if frappe.db.exists("User", email):
		return email
	frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
	).insert(ignore_permissions=True)
	return email


class TestNotifications(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	@patch("frappe.desk.form.assign_to._add")
	def test_submission_received_assigns_a_real_task(self, mock_assign):
		notifications.notify_submission_received("SUB-REV-001", "manager@example.com")

		mock_assign.assert_called_once()
		(args,), kwargs = mock_assign.call_args
		self.assertEqual(args["doctype"], "EGC Submittal Revision")
		self.assertEqual(args["name"], "SUB-REV-001")
		self.assertEqual(args["assign_to"], ["manager@example.com"])
		self.assertTrue(kwargs.get("ignore_permissions"))

	@patch("frappe.desk.form.assign_to._add")
	def test_submission_received_skips_when_no_manager(self, mock_assign):
		notifications.notify_submission_received("SUB-REV-001", None)
		mock_assign.assert_not_called()

	@patch("frappe.desk.form.assign_to._add")
	def test_response_recorded_assigns_a_task_to_every_recipient(self, mock_assign):
		notifications.notify_response_recorded("SUB-REV-001", "Approved", ["a@example.com", "b@example.com"])

		# `_assign_task` assigns one user per call (assign_to._add's own shape), not a single
		# call with a multi-user list.
		assigned_to = {call.args[0]["assign_to"][0] for call in mock_assign.call_args_list}
		self.assertEqual(assigned_to, {"a@example.com", "b@example.com"})

	@patch("frappe.desk.form.assign_to._add")
	def test_response_recorded_drops_administrator_from_recipients(self, mock_assign):
		notifications.notify_response_recorded("SUB-REV-001", "Approved", ["Administrator", "a@example.com"])

		mock_assign.assert_called_once()
		(args,), _ = mock_assign.call_args
		self.assertEqual(args["assign_to"], ["a@example.com"])

	@patch("frappe.desk.form.assign_to._add")
	def test_new_revision_assigns_a_real_task(self, mock_assign):
		notifications.notify_new_revision("SUB-001", "SUB-001-S01", ["manager@example.com"])

		mock_assign.assert_called_once()
		(args,), _ = mock_assign.call_args
		self.assertEqual(args["doctype"], "EGC Submittal")
		self.assertEqual(args["name"], "SUB-001")
		self.assertEqual(args["assign_to"], ["manager@example.com"])

	@patch("frappe.desk.form.assign_to._add")
	def test_notify_with_no_real_recipients_never_assigns(self, mock_assign):
		# Every recipient falsy/Administrator — _assign_task must short-circuit before calling out.
		notifications.notify_response_recorded("SUB-REV-001", "Approved", ["Administrator", None, ""])
		mock_assign.assert_not_called()

	@patch("frappe.desk.form.assign_to._add")
	def test_activity_assigned_assigns_a_real_task(self, mock_assign):
		company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
		project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"EGC-Notif-Act-{frappe.generate_hash(length=8)}", "company": company}
		).insert(ignore_permissions=True)
		activity = frappe.get_doc(
			{
				"doctype": "EGC Activity",
				"project": project.name,
				"activity_code": "NOTIF-ACT",
				"activity_name": "Notification Fixture",
			}
		).insert(ignore_permissions=True)

		notifications.notify_activity_assigned(activity.name, "person@example.com", "Responsible")

		mock_assign.assert_called_once()
		(args,), _ = mock_assign.call_args
		self.assertEqual(args["doctype"], "EGC Activity")
		self.assertEqual(args["name"], activity.name)
		self.assertEqual(args["assign_to"], ["person@example.com"])
		self.assertIn("NOTIF-ACT", args["description"])

	@patch("frappe.desk.form.assign_to._add")
	def test_activity_assigned_skips_when_no_person(self, mock_assign):
		notifications.notify_activity_assigned("SOME-ACT", None, "Responsible")
		mock_assign.assert_not_called()

	@patch("egc_projects.egc_projects.notifications.enqueue_create_notification")
	def test_activity_due_date_reminder_dedupe_key_bakes_in_the_date(self, mock_enqueue):
		from frappe.utils import add_days, today

		from egc_projects.egc_projects import assignments

		company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
		project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"EGC-Notif-Due-{frappe.generate_hash(length=8)}", "company": company}
		).insert(ignore_permissions=True)
		activity = frappe.get_doc(
			{
				"doctype": "EGC Activity",
				"project": project.name,
				"activity_code": "NOTIF-DUE",
				"activity_name": "Due Date Fixture",
				"planned_end_date": add_days(today(), -1),
			}
		).insert(ignore_permissions=True)
		assignee = _get_or_create_user("egc-notif-activity-assignee@example.com")
		with patch("frappe.desk.form.assign_to._add"):
			assignments.add_assignment("EGC Activity", activity.name, "Responsible", person=assignee)

		notifications.send_activity_due_date_reminders()

		matching_calls = [c for c in mock_enqueue.call_args_list if c.args[0] == [assignee]]
		self.assertEqual(len(matching_calls), 1, mock_enqueue.call_args_list)
		args, kwargs = matching_calls[0]
		self.assertEqual(kwargs.get("dedupe_on"), ["document_type", "document_name", "subject"])
		self.assertIn(str(today()), args[1]["subject"])
		self.assertIn("NOTIF-DUE", args[1]["subject"])

	@patch("egc_projects.egc_projects.notifications.enqueue_create_notification")
	def test_due_date_reminder_dedupe_key_bakes_in_the_date(self, mock_enqueue):
		# send_due_date_reminders() intentionally uses a DIFFERENT dedupe strategy from the three
		# event notifiers above (documented in its own docstring): the daily job's dedupe key is
		# only effective because today's date is baked into the subject text itself. Built with a
		# real fixture rather than asserting a global "nothing is open" — this function scans
		# every open review step on the SITE, not one project, and the standing demo project
		# (KFSH MRI Expansion) genuinely has a live pending review, so a global-emptiness
		# assumption would be exactly the "must never depend on live site data" trap CLAUDE.md
		# warns about.
		from frappe.utils import add_days, today

		reviewer = _get_or_create_user("egc-notif-reviewer@example.com")
		company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
		project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"EGC-Notif-Test-{frappe.generate_hash(length=8)}", "company": company}
		).insert(ignore_permissions=True)
		submittal_type = frappe.get_all("EGC Submittal Type", limit=1, pluck="name")[0]
		submittal = frappe.get_doc(
			{
				"doctype": "EGC Submittal",
				"project": project.name,
				"submittal_number": f"NOTIF-{frappe.generate_hash(length=6)}",
				"title": "Notification Dedupe Fixture",
				"submittal_type": submittal_type,
			}
		).insert(ignore_permissions=True)
		revision = frappe.get_doc(
			{
				"doctype": "EGC Submittal Revision",
				"submittal": submittal.name,
				"revision_label": "00",
				"due_date": add_days(today(), -1),
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "EGC Submittal Review Step",
				"submittal_revision": revision.name,
				"sequence": 1,
				"reviewer_user": reviewer,
				"status": "In Review",
			}
		).insert(ignore_permissions=True)

		notifications.send_due_date_reminders()

		# This function scans every open review step on the whole SITE (see docstring above) — a
		# genuinely live dev site can have other real pending reviews at the same time, so assert
		# THIS fixture's own call happened, not that it was the only one.
		matching_calls = [c for c in mock_enqueue.call_args_list if c.args[0] == [reviewer]]
		self.assertEqual(len(matching_calls), 1, mock_enqueue.call_args_list)
		args, kwargs = matching_calls[0]
		self.assertEqual(kwargs.get("dedupe_on"), ["document_type", "document_name", "subject"])
		self.assertIn(str(today()), args[1]["subject"])
