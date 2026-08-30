"""My Open Items — an extensible action-item registry (docs/ARCHITECTURE_V2.md §8).

A plain registry, the same shape as `relationships.ALLOWED_LINK_DOCTYPES`, not a generic
DocType-based framework — adding a future source (RFI Response, MIR Review, ...) is a new
function plus one more line in `get_open_items_for_user`, not a schema change.

Every source returns the same normalised shape: `{source, title, doctype, name, project,
due_date, is_overdue, url}`.
"""

from __future__ import annotations

import frappe
from frappe.utils import get_url_to_form, getdate, today

from egc_projects.egc_projects.doctype.egc_activity.egc_activity import is_overdue


def _submittal_review_items(user: str, project: str | None) -> list[dict]:
	filters = {"reviewer_user": user, "status": "In Review"}
	steps = frappe.get_all(
		"EGC Submittal Review Step",
		filters=filters,
		fields=["name", "submittal_revision", "project"],
	)
	if project:
		steps = [s for s in steps if s.project == project]
	if not steps:
		return []

	revisions = {
		r.name: r
		for r in frappe.get_all(
			"EGC Submittal Revision",
			filters={"name": ("in", [s.submittal_revision for s in steps])},
			fields=["name", "submittal", "due_date"],
		)
	}
	submittals = {
		s.name: s
		for s in frappe.get_all(
			"EGC Submittal",
			filters={"name": ("in", list({r.submittal for r in revisions.values()}))},
			fields=["name", "submittal_number", "title", "project"],
		)
	}

	today_date = getdate(today())
	items = []
	for step in steps:
		revision = revisions.get(step.submittal_revision)
		if not revision:
			continue
		submittal = submittals.get(revision.submittal)
		if not submittal:
			continue
		due_date = revision.due_date
		items.append(
			{
				"source": "submittal_review",
				"title": f"{submittal.submittal_number} — {submittal.title}",
				"doctype": "EGC Submittal",
				"name": submittal.name,
				"project": submittal.project,
				"due_date": due_date,
				"is_overdue": bool(due_date and getdate(due_date) < today_date),
				"url": get_url_to_form("EGC Submittal", submittal.name),
			}
		)
	return items


def _overdue_activity_items(user: str, project: str | None) -> list[dict]:
	# Multi-person assignment (assignments.py): "responsible for" is no longer a single field on
	# Activity — it's every EGC Assignment row whose `person` (a User, directly) is this session's
	# user, regardless of assignment_role (Responsible/Assignee/Supervisor/... all mean "this is
	# on my plate" for the purposes of My Open Items).
	activity_names = frappe.get_all(
		"EGC Assignment",
		filters={"parent_doctype": "EGC Activity", "person": user},
		pluck="parent_name",
	)
	if not activity_names:
		return []

	filters = {"name": ("in", activity_names)}
	if project:
		filters["project"] = project
	activities = frappe.get_all(
		"EGC Activity",
		filters=filters,
		fields=["name", "activity_code", "activity_name", "project", "status", "planned_end_date"],
	)

	items = []
	for activity in activities:
		if not is_overdue(activity.status, activity.planned_end_date):
			continue
		items.append(
			{
				"source": "activity_overdue",
				"title": f"{activity.activity_code} — {activity.activity_name}",
				"doctype": "EGC Activity",
				"name": activity.name,
				"project": activity.project,
				"due_date": activity.planned_end_date,
				"is_overdue": True,
				"url": get_url_to_form("EGC Activity", activity.name),
			}
		)
	return items


def get_open_items_for_user(user: str, project: str | None = None) -> list[dict]:
	"""Every open action item assigned to `user`, normalised across sources, soonest-due first.

	Items with no due date sort last, not first — an undated item is not more urgent than a
	dated one, which is the same convention `api/hub.py`'s overdue counters already use.
	"""
	items = _submittal_review_items(user, project) + _overdue_activity_items(user, project)
	items.sort(key=lambda item: (item["due_date"] is None, item["due_date"]))
	return items
