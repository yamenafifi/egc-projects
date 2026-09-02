# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for `notifications.notify_watchers` and its wiring into `submittal_control.py` — a
`EGC Assignment` "Watcher" (a party who tracks a Submittal's progress without ever being asked to
approve anything) gets in-app visibility on every ball-in-court move, but an email only at the
two moments actually worth an inbox interruption: submission received and final response — never
on an intermediate forward/stage-advance hop. `frappe.flags.mute_emails` mirrors
test_notifications_email.py's own pattern.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from egc_projects.egc_projects import assignments, constants as c, notifications, submittal_control


def _make_company():
	return frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]


def _make_project(company):
	doc = frappe.get_doc(
		{"doctype": "Project", "project_name": f"EGC-NotifyWatchers-Test-{frappe.generate_hash(length=8)}", "company": company}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_user(email, roles=()):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0})
		user.insert(ignore_permissions=True)
	if roles:
		user.add_roles(*roles)
	return user.name


def _make_private_file():
	f = frappe.get_doc({"doctype": "File", "file_name": f"{frappe.generate_hash(length=6)}.txt", "is_private": 1, "content": "x"})
	f.insert(ignore_permissions=True)
	return f.file_url


class TestNotifyWatchers(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		frappe.flags.mute_emails = True
		cls.company = _make_company()
		if not frappe.db.exists("EGC Document Type", "Drawing"):
			frappe.get_doc({"doctype": "EGC Document Type", "document_type_name": "Drawing", "is_drawing": 1}).insert(ignore_permissions=True)
		if not frappe.db.exists("EGC Discipline", "MECH"):
			frappe.get_doc({"doctype": "EGC Discipline", "discipline_code": "MECH", "discipline_name": "Mechanical"}).insert(ignore_permissions=True)
		if not frappe.db.exists("EGC Submittal Type", "EGC-NotifyWatchers-Type"):
			frappe.get_doc({"doctype": "EGC Submittal Type", "submittal_type_name": "EGC-NotifyWatchers-Type"}).insert(ignore_permissions=True)
		cls.reviewer = _get_or_create_user("egc-nw-reviewer@example.com", [c.ROLE_PROJECT_VIEWER])
		cls.watcher = _get_or_create_user("egc-nw-watcher@example.com", [c.ROLE_PROJECT_VIEWER])
		cls.low_privilege_user = _get_or_create_user("egc-nw-lowpriv@example.com", [c.ROLE_EXTERNAL_VIEWER])

	@classmethod
	def tearDownClass(cls):
		frappe.flags.mute_emails = False
		super().tearDownClass()

	def setUp(self):
		self.project = _make_project(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")

	def _make_submittal(self, add_watcher=True):
		doc = frappe.get_doc(
			{
				"doctype": "EGC Submittal",
				"project": self.project,
				"submittal_number": f"SUB-NW-{frappe.generate_hash(length=6)}",
				"title": "Notify Watchers Test Submittal",
				"submittal_type": "EGC-NotifyWatchers-Type",
			}
		)
		doc.insert(ignore_permissions=True)
		if add_watcher:
			assignments.add_assignment("EGC Submittal", doc.name, "Watcher", person=self.watcher)
		return doc.name

	def _make_submission_with_single_reviewer(self, submittal):
		document = frappe.get_doc(
			{
				"doctype": "EGC Project Document",
				"project": self.project,
				"document_number": f"DOC-NW-{frappe.generate_hash(length=6)}",
				"title": "Notify Watchers Test Document",
				"document_type": "Drawing",
				"discipline": "MECH",
			}
		)
		document.insert(ignore_permissions=True)
		revision = frappe.get_doc(
			{"doctype": "EGC Project Document Revision", "document": document.name, "revision": "00", "file": _make_private_file(), "revision_date": today()}
		)
		revision.insert(ignore_permissions=True)
		revision.submit()

		submission = frappe.get_doc({"doctype": "EGC Submittal Revision", "submittal": submittal, "revision_label": "00", "date_submitted": today()})
		submission.append("documents", {"document_revision": revision.name})
		submission.insert(ignore_permissions=True)

		step = frappe.get_doc(
			{
				"doctype": "EGC Submittal Review Step",
				"submittal_revision": submission.name,
				"sequence": 0,
				"reviewer_user": self.reviewer,
				"reviewer_label": self.reviewer,
				"is_required": 1,
			}
		)
		step.insert(ignore_permissions=True)
		return submission, step

	# -- direct unit coverage of notify_watchers itself -----------------------------------------

	def test_in_app_notification_regardless_of_actionable(self):
		submittal = self._make_submittal()
		before = frappe.db.count("Notification Log", {"for_user": self.watcher})
		notifications.notify_watchers(submittal, "Test subject", "Test body", actionable=False)
		self.assertEqual(frappe.db.count("Notification Log", {"for_user": self.watcher}), before + 1)

	def test_email_only_when_actionable(self):
		submittal = self._make_submittal()

		before = frappe.db.count("Email Queue")
		notifications.notify_watchers(submittal, "Not actionable", "body", actionable=False)
		self.assertEqual(frappe.db.count("Email Queue"), before)

		notifications.notify_watchers(submittal, "Actionable", "body", actionable=True)
		self.assertEqual(frappe.db.count("Email Queue"), before + 1)

	def test_no_watchers_is_a_silent_no_op(self):
		submittal = self._make_submittal(add_watcher=False)
		before_notif = frappe.db.count("Notification Log")
		before_email = frappe.db.count("Email Queue")
		notifications.notify_watchers(submittal, "subject", "body", actionable=True)
		self.assertEqual(frappe.db.count("Notification Log"), before_notif)
		self.assertEqual(frappe.db.count("Email Queue"), before_email)

	def test_survives_a_low_privilege_session(self):
		submittal = self._make_submittal()
		frappe.set_user(self.low_privilege_user)
		# Must not raise, even though this user has no read permission on EGC Submittal / EGC
		# Assignment — the whole point of the raw query instead of assignments.get_assignments_for.
		notifications.notify_watchers(submittal, "subject", "body", actionable=True)

	# -- wiring into the real engine ------------------------------------------------------------
	#
	# Counted by recipient, not by a raw Email Queue row delta: a real `.submit()` also exercises
	# the pre-existing reviewer ball-in-court email (`send_ball_in_court_email`), which — only
	# inside `IntegrationTestCase`'s own transaction wrapping, not in a plain top-level call —
	# occasionally queues twice for reasons unrelated to this feature (confirmed via a standalone
	# reproduction outside the test harness, which queues exactly once as expected). Asserting on
	# the watcher's own recipient count sidesteps that unrelated noise and tests the actual claim.

	def _watcher_email_count(self):
		return frappe.db.count("Email Queue Recipient", {"recipient": self.watcher})

	def test_submission_received_emails_watcher_once(self):
		submittal = self._make_submittal()
		submission, step = self._make_submission_with_single_reviewer(submittal)

		before = self._watcher_email_count()
		submission.submit()
		self.assertEqual(self._watcher_email_count(), before + 1)

	def test_forward_hop_does_not_email_watcher(self):
		submittal = self._make_submittal()
		submission, step = self._make_submission_with_single_reviewer(submittal)
		submission.submit()

		other_reviewer = _get_or_create_user("egc-nw-reviewer-2@example.com", [c.ROLE_PROJECT_VIEWER])
		before = self._watcher_email_count()
		submittal_control.record_step_response(step.name, c.RESPONSE_APPROVED, forward_to_user=other_reviewer)
		self.assertEqual(self._watcher_email_count(), before)

	def test_final_response_emails_watcher(self):
		submittal = self._make_submittal()
		submission, step = self._make_submission_with_single_reviewer(submittal)
		submission.submit()

		before = self._watcher_email_count()
		submittal_control.record_step_response(step.name, c.RESPONSE_APPROVED)
		self.assertEqual(self._watcher_email_count(), before + 1)
