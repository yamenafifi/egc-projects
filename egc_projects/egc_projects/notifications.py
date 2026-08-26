"""Submittal notifications (docs/ARCHITECTURE_V2.md §7).

Ball-in-court delivery is `frappe.desk.form.assign_to` — see `submittal_control.py`'s
`_assign_step`/`_close_step_assignment`. Assigning a ToDo already creates a `Notification Log`
entry and surfaces the item in that user's assignment list for free, so it is not duplicated
here. This module covers the remaining events the brief asks for: submission received, response
recorded, revise & resubmit, new revision submitted, upcoming due date, overdue — all via the
documented core helper `enqueue_create_notification`, never a parallel notification store.
"""

from __future__ import annotations

import frappe
from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification
from frappe.utils import add_days, getdate, today


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


def notify_submission_received(submission: str, submittal_manager: str | None) -> None:
	if not submittal_manager:
		return
	label = frappe.db.get_value("EGC Submittal Revision", submission, "revision_label")
	_notify(
		[submittal_manager],
		"EGC Submittal Revision",
		submission,
		frappe._("Submission {0} received for review").format(label or submission),
	)


def notify_response_recorded(submission: str, response: str, notify_users: list[str]) -> None:
	label = frappe.db.get_value("EGC Submittal Revision", submission, "revision_label")
	_notify(
		notify_users,
		"EGC Submittal Revision",
		submission,
		frappe._("{0}: {1}").format(label or submission, response),
	)


def notify_new_revision(submittal_name: str, new_submission: str, notify_users: list[str]) -> None:
	label = frappe.db.get_value("EGC Submittal Revision", new_submission, "revision_label")
	_notify(
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
