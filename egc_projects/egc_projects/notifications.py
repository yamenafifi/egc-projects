"""Submittal and Activity notifications (docs/ARCHITECTURE_V2.md §7).

Ball-in-court delivery is `frappe.desk.form.assign_to` — see `submittal_control.py`'s
`_assign_step`/`_close_step_assignment`, and this module's own `_assign_task` below, which
mirrors it for the submittal_manager/originator roles: submission received, response recorded,
new revision submitted all create a real ToDo, not just a bell — a passive Notification Log
alone is easy to miss and does not read as an actual task. Assigning a ToDo already creates a
`Notification Log` entry for free, so `_assign_task` events are never ALSO passed through
`_notify`. `send_due_date_reminders`/`send_activity_due_date_reminders` are the one event-family
left on plain `_notify` — an in-app-only reminder ping, not a new actionable task each time it
fires (the actual task was already created once, at assignment time).

Activities were a real gap until now: `assignments.py` had no notification of any kind for being
added to (or removed from) an Activity's team, and no scheduled job ever reminded anyone an
Activity was overdue — `notify_activity_assigned`/`send_activity_due_date_reminders` close that
gap, mirroring the Submittal pattern exactly.

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


def notify_activity_assigned(activity: str, person: str, assignment_role: str) -> None:
	"""A real ToDo when someone is added to an Activity's team — called from
	`assignments.add_assignment` whenever `parent_doctype == "EGC Activity"` and a `person` (not
	just a bare organization) is named. Mirrors `notify_submission_received`'s parity fix exactly:
	being assigned to a real piece of work is a task, not just a bell."""
	if not person:
		return
	activity_doc = frappe.db.get_value("EGC Activity", activity, ["activity_code", "activity_name"], as_dict=True)
	label = f"{activity_doc.activity_code}: {activity_doc.activity_name}" if activity_doc else activity
	_assign_task(
		[person],
		"EGC Activity",
		activity,
		frappe._("Assigned to {0} as {1}").format(label, assignment_role),
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


def send_activity_due_date_reminders() -> None:
	"""Daily scheduled task (see hooks.py `scheduler_events`) — the Activity-side counterpart of
	`send_due_date_reminders` above. Reminds every person assigned to an Activity approaching or
	past its `planned_end_date`, once per day, same dedupe strategy (today's date baked into the
	subject). This is a reminder ONLY: the actual "you're responsible for this" task was already
	created once, at assignment time, by `notify_activity_assigned` — this just nudges it as the
	date approaches or passes, exactly like the Submittal reminder nudges an already-assigned
	review step rather than creating a second one."""
	from egc_projects.egc_projects import constants as c
	from egc_projects.egc_projects.doctype.egc_activity.egc_activity import is_overdue

	today_date = getdate(today())
	warn_from = add_days(today_date, 2)

	# Groups are included deliberately, not just leaves — a group's `planned_end_date` is rollup-
	# derived (activity_control.py), but that doesn't make it any less real: someone can genuinely
	# be "Responsible" for a whole phase, and this only reads current state, not reacting to a
	# specific edit event, so there's no engine-authority concern the way a direct write would have.
	activities = frappe.get_all(
		"EGC Activity",
		filters={"status": ("not in", c.ACTIVITY_CLOSED_STATUSES), "planned_end_date": ("is", "set")},
		fields=["name", "activity_code", "activity_name", "status", "planned_end_date"],
	)
	due_soon = [row for row in activities if getdate(row.planned_end_date) <= warn_from]
	if not due_soon:
		return

	assignments = frappe.get_all(
		"EGC Assignment",
		filters={"parent_doctype": "EGC Activity", "parent_name": ("in", [row.name for row in due_soon]), "person": ("is", "set")},
		fields=["parent_name", "person"],
	)
	people_by_activity: dict[str, list[str]] = {}
	for row in assignments:
		people_by_activity.setdefault(row.parent_name, []).append(row.person)

	for row in due_soon:
		people = people_by_activity.get(row.name)
		if not people:
			continue

		label = (
			frappe._("Overdue since {0}").format(frappe.format(row.planned_end_date, {"fieldtype": "Date"}))
			if is_overdue(row.status, row.planned_end_date)
			else frappe._("Due {0}").format(frappe.format(row.planned_end_date, {"fieldtype": "Date"}))
		)
		subject = frappe._("{0} — {1}: {2} ({3})").format(label, row.activity_code, row.activity_name, today_date)
		_notify(
			people,
			"EGC Activity",
			row.name,
			subject,
			dedupe_on=["document_type", "document_name", "subject"],
		)


def _send_email(
	user: str,
	subject: str,
	title: str,
	body: str,
	button_label: str | None = None,
	button_url: str | None = None,
) -> None:
	"""Every email this app sends goes through here, styled exactly like Frappe's own
	transactional emails (password reset, login-by-link, user invitation) — `with_container=True`
	is what actually wraps the content below in the branded card (logo/header/footer) seen on
	every core Frappe email; without it `frappe.sendmail` renders the bare `message` HTML with no
	wrapper at all, which is what this app's own emails looked like before this fix. The
	`email-header-title`/`btn btn-primary`/`text-muted text-small` classes aren't decoration —
	they're the exact vocabulary `frappe/templates/emails/login_with_email_link.html` itself uses,
	styled for free by the same CSS `with_container` pulls in.
	"""
	if not user or user == "Administrator":
		return
	email = frappe.db.get_value("User", user, "email") or user

	content = f'<h1 class="email-header-title">{frappe.utils.escape_html(title)}</h1>'
	content += f"<p>{body}</p>"
	if button_label and button_url:
		content += f'<p><a href="{button_url}" class="btn btn-primary">{frappe.utils.escape_html(button_label)}</a></p>'

	frappe.sendmail(
		recipients=[email],
		sender=NOTIFY_SENDER,
		subject=subject,
		message=content,
		with_container=True,
		now=True,
	)


def send_ball_in_court_email(reviewer_user: str, submission: str) -> None:
	"""Emails the reviewer a step just got assigned to — called from `_assign_step`
	(submittal_control.py), the exact same moment that already creates the in-app assignment."""
	revision = frappe.db.get_value(
		"EGC Submittal Revision", submission, ["revision_label", "project"], as_dict=True
	)
	if not revision:
		return
	label = revision.revision_label or submission
	url = f"{get_url()}/app/egc-project-hub/{revision.project}/submittals"
	_send_email(
		reviewer_user,
		frappe._("Review requested: {0}").format(label),
		frappe._("Review requested"),
		frappe._("You've been asked to review {0}.").format(frappe.bold(label)),
		button_label=frappe._("Open in Project Manager"),
		button_url=url,
	)


def send_directory_welcome_email(user: str, project: str) -> None:
	"""Sent once, from `grant_portal_access` (api/directory.py), the moment a Directory entry is
	first given Portal Access — not on every later change to their access."""
	project_name = frappe.db.get_value("Project", project, "project_name") or project
	url = f"{get_url()}/app/egc-project-hub/{project}"
	_send_email(
		user,
		frappe._("You've been added to {0}").format(project_name),
		frappe._("You've been added to {0}").format(project_name),
		frappe._("You now have access to {0} in EGC Project Manager.").format(frappe.bold(project_name)),
		button_label=frappe._("Open the Project"),
		button_url=url,
	)
