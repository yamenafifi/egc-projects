"""Submittal notifications (docs/ARCHITECTURE_V2.md §7).

Ball-in-court delivery is `frappe.desk.form.assign_to` — see `submittal_control.py`'s
`_assign_step`/`_close_step_assignment`, and this module's own `_assign_task` below, which
mirrors it for the submittal_manager/originator roles: submission received, response recorded,
new revision submitted all create a real ToDo, not just a bell — a passive Notification Log
alone is easy to miss and does not read as an actual task. Assigning a ToDo already creates a
`Notification Log` entry for free, so `_assign_task` events are never ALSO passed through
`_notify`. `send_due_date_reminders` is the one event-family left on plain `_notify` — an
in-app-only reminder ping, not a new actionable task each time it fires.

**Email** (`send_ball_in_court_email`/`send_directory_welcome_email` below) is a separate,
additive channel on top of all of the above — the in-app Notification Log stays exactly as it
was, this just also reaches an inbox for the two events most worth a real email: a reviewer
just got a step assigned to them, and someone was just given Hub access for the first time.
Deliberately simple for this first pass — plain text, no `Email Template` doctype, one shared
`no-reply@egc-me.com` sender rather than the site's general default outgoing account (so this
keeps working correctly even if that default is ever repointed at a different mailbox).
"""

from __future__ import annotations

import frappe
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.utils import add_days, get_url, getdate, today

NOTIFY_SENDER = "no-reply@egc-me.com"


def _notify(users: list[str], doctype: str, name: str, subject: str, dedupe_on: list[str] | None = None) -> None:
	users = [u for u in dict.fromkeys(users) if u and u != "Administrator"]
	if not users:
		return
	enqueue_create_notification(
		users,
		{
			"type": "Alert",
			"document_type": doctype,
			"document_name": name,
			"subject": subject,
		},
		dedupe_on=dedupe_on,
	)


def _assign_task(users: list[str], doctype: str, name: str, description: str) -> None:
	"""A real, actionable Frappe ToDo — not just a bell — mirroring `submittal_control.py`'s own
	`_assign_step` (the proven ball-in-court pattern). `assign_to._add` already creates its own
	Notification Log entry as a side effect, so callers never also pass the same event through
	`_notify`. Each `submittal_control.py` call site already fires this once per genuine lifecycle
	event (submit, response, new revision) — never in a retry loop — so no dedupe guard is needed
	here the way `_notify`'s callers need `dedupe_on`."""
	from frappe.desk.form.assign_to import _add as assign_add

	for user in dict.fromkeys(u for u in users if u and u != "Administrator"):
		assign_add(
			{
				"doctype": doctype,
				"name": name,
				"assign_to": [user],
				"description": description,
			},
			ignore_permissions=True,
		)


def notify_submission_received(submission: str, submittal_manager: str | None) -> None:
	if not submittal_manager:
		return
	label = frappe.db.get_value("EGC Submittal Revision", submission, "revision_label")
	_assign_task(
		[submittal_manager],
		"EGC Submittal Revision",
		submission,
		frappe._("Submission {0} received for review").format(label or submission),
	)


def notify_response_recorded(submission: str, response: str, notify_users: list[str]) -> None:
	label = frappe.db.get_value("EGC Submittal Revision", submission, "revision_label")
	_assign_task(
		notify_users,
		"EGC Submittal Revision",
		submission,
		frappe._("{0}: {1}").format(label or submission, response),
	)


def notify_new_revision(submittal_name: str, new_submission: str, notify_users: list[str]) -> None:
	label = frappe.db.get_value("EGC Submittal Revision", new_submission, "revision_label")
	_assign_task(
		notify_users,
		"EGC Submittal",
		submittal_name,
		frappe._("New submission {0} created").format(label or new_submission),
	)


def send_due_date_reminders() -> None:
	"""Daily scheduled task (see hooks.py `scheduler_events`), mirroring `egc_hr`'s own
	`alert_expiring_documents` pattern. Reminds each reviewer with an open review step due soon
	or overdue, once per day — `dedupe_on` keys on the step so a reviewer is never notified
	twice for the same step on the same day even if the job somehow ran twice.
	"""
	today_date = getdate(today())
	warn_from = add_days(today_date, 2)

	rows = frappe.get_all(
		"EGC Submittal Review Step",
		filters={"status": "In Review", "reviewer_user": ("is", "set")},
		fields=["name", "reviewer_user", "submittal_revision"],
	)
	if not rows:
		return

	revision_names = {row.submittal_revision for row in rows}
	due_dates = frappe.get_all(
		"EGC Submittal Revision",
		filters={"name": ("in", list(revision_names))},
		fields=["name", "due_date", "revision_label"],
	)
	due_by_revision = {row.name: row for row in due_dates}

	for row in rows:
		revision = due_by_revision.get(row.submittal_revision)
		if not revision or not revision.due_date:
			continue

		due = getdate(revision.due_date)
		if due > warn_from:
			continue

		# `_notification_exists`'s dedupe check has no date bound — it matches on field values
		# alone, forever. Baking today's date into the subject is what turns "once ever" into
		# "once per day": tomorrow's subject text differs, so tomorrow's reminder is not
		# suppressed by today's already-existing Notification Log row.
		label = (
			frappe._("Overdue since {0}").format(frappe.format(revision.due_date, {"fieldtype": "Date"}))
			if due < today_date
			else frappe._("Due {0}").format(frappe.format(revision.due_date, {"fieldtype": "Date"}))
		)
		subject = frappe._("{0} — submission {1} needs your review ({2})").format(
			label, revision.revision_label, today_date
		)
		_notify(
			[row.reviewer_user],
			"EGC Submittal Review Step",
			row.name,
			subject,
			dedupe_on=["document_type", "document_name", "subject"],
		)


def _send_email(user: str, subject: str, message: str) -> None:
	if not user or user == "Administrator":
		return
	email = frappe.db.get_value("User", user, "email") or user
	frappe.sendmail(recipients=[email], sender=NOTIFY_SENDER, subject=subject, message=message, now=True)


def send_ball_in_court_email(reviewer_user: str, submission: str) -> None:
	"""Emails the reviewer a step just got assigned to — called from `_assign_step`
	(submittal_control.py), the exact same moment that already creates the in-app assignment."""
	revision = frappe.db.get_value(
		"EGC Submittal Revision", submission, ["revision_label", "project"], as_dict=True
	)
	if not revision:
		return
	url = f"{get_url()}/app/egc-project-hub/{revision.project}/submittals"
	_send_email(
		reviewer_user,
		frappe._("Review requested: {0}").format(revision.revision_label or submission),
		frappe._('You\'ve been asked to review {0}.<br><br><a href="{1}">Open in Project Manager</a>').format(
			revision.revision_label or submission, url
		),
	)


def send_directory_welcome_email(user: str, project: str) -> None:
	"""Sent once, from `grant_portal_access` (api/directory.py), the moment a Directory entry is
	first given Portal Access — not on every later change to their access."""
	project_name = frappe.db.get_value("Project", project, "project_name")
	url = f"{get_url()}/app/egc-project-hub/{project}"
	_send_email(
		user,
		frappe._("You've been added to {0}").format(project_name or project),
		frappe._('You now have access to {0} in EGC Project Manager.<br><br><a href="{1}">Open the project</a>').format(
			project_name or project, url
		),
	)
