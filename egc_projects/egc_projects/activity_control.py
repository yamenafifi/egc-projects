"""Activity schedule rollup engine (docs/ARCHITECTURE_V2.md §5).

This module is the SINGLE place that computes or writes a group Activity's `percent_complete`,
`planned_start_date`, `planned_end_date`, `actual_start_date`, `actual_end_date`, `duration_days`
and `status`. These fields are read-only on a group Activity by DocType declaration
(`read_only_depends_on: "eval:doc.is_group"`); this engine is what actually keeps them honest
server-side, mirroring `document_control.py`'s single-writer discipline.

A leaf Activity's own `duration_days` is computed by the `EGC Activity` controller itself
(docs/ARCHITECTURE_V2.md §5: "computed in the controller, not stored via a separate engine call
for a leaf") — only rollup values, which require walking a group's children, live here.

All writes below use `frappe.db.set_value`, which does not invoke controller hooks, so refreshing
a rollup never re-enters `EGC Activity.validate()` and never re-triggers `on_update`/`on_trash`.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import date_diff, flt

from egc_projects.egc_projects import constants as c

#: Flag name checked by `assert_group_fields_not_hand_edited` to distinguish an engine-originated
#: write from a user's own edit. The engine's writes go through `frappe.db.set_value`, which never
#: runs `validate()` at all, so this is only ever consulted on a genuine `save()` path — it is set
#: here anyway, in case a future write path through this module ever goes through `save()`.
ENGINE_FLAG = "egc_activity_engine"

#: The fields a group Activity may never hand-edit — they are derived from its direct children.
ROLLUP_FIELDS = (
	"percent_complete",
	"planned_start_date",
	"planned_end_date",
	"actual_start_date",
	"actual_end_date",
	"duration_days",
	"status",
)

_CHILD_FIELDS = (
	"name",
	"status",
	"percent_complete",
	"planned_start_date",
	"planned_end_date",
	"actual_start_date",
	"actual_end_date",
)


def assert_group_fields_not_hand_edited(doc) -> None:
	"""Reject a direct edit of a group Activity's rollup-owned fields.

	A brand-new group has no children yet to roll up from, so its initial values (whatever the
	create form submitted, typically just the field defaults) are left alone here — there is
	nothing yet to protect. Once the group exists, any further attempt to change one of
	`ROLLUP_FIELDS` outside the engine itself is rejected, exactly like
	`document_control.assert_engine_authorized` guards `revision_status`/`superseded_by`.
	"""
	if frappe.flags.get(ENGINE_FLAG) or not doc.is_group or doc.is_new():
		return

	for fieldname in ROLLUP_FIELDS:
		if doc.has_value_changed(fieldname):
			frappe.throw(
				_(
					"{0} is derived from this group Activity's children and cannot be"
					" edited directly."
				).format(_(doc.meta.get_label(fieldname))),
				title=_("Not Allowed"),
				exc=frappe.ValidationError,
			)


def _engine_set(activity: str, values: dict) -> None:
	frappe.flags[ENGINE_FLAG] = True
	try:
		frappe.db.set_value("EGC Activity", activity, values, update_modified=False)
	finally:
		frappe.flags[ENGINE_FLAG] = False


def _duration(start, end) -> int:
	# `duration_days` is an Int fieldtype, and Frappe's numeric columns are NOT NULL DEFAULT 0
	# at the schema level — a normal `doc.save()` already coerces a Python `None` to `0` for any
	# numeric field (`cint(None) == 0` in `get_valid_dict`), but `frappe.db.set_value` writes
	# straight to SQL with no such coercion and throws `IntegrityError` on a raw `None` here. `0`
	# is unambiguous as "not computed": the formula below can never itself produce 0 (a same-day
	# span is `date_diff(x, x) + 1 == 1`), so 0 cannot collide with a real duration.
	if start and end:
		return date_diff(end, start) + 1
	return 0


def _rollup_status(children: list[frappe._dict]) -> str:
	"""all Completed -> Completed; all Not Started -> Not Started; else In Progress.

	`Cancelled` children are excluded from the set this rule is evaluated over — a cancelled
	sibling must not force its parent's status either way. If every child is cancelled, there is
	nothing left to aggregate over, so the group itself is treated as Cancelled.
	"""
	live = [child for child in children if child.status != c.ACTIVITY_CANCELLED]
	if not live:
		return c.ACTIVITY_CANCELLED
	if all(child.status == c.ACTIVITY_COMPLETED for child in live):
		return c.ACTIVITY_COMPLETED
	if all(child.status == c.ACTIVITY_NOT_STARTED for child in live):
		return c.ACTIVITY_NOT_STARTED
	return c.ACTIVITY_IN_PROGRESS


def _compute_rollup(children: list[frappe._dict]) -> dict:
	planned_starts = [child.planned_start_date for child in children if child.planned_start_date]
	planned_ends = [child.planned_end_date for child in children if child.planned_end_date]
	actual_starts = [child.actual_start_date for child in children if child.actual_start_date]
	actual_ends = [child.actual_end_date for child in children if child.actual_end_date]

	planned_start_date = min(planned_starts) if planned_starts else None
	planned_end_date = max(planned_ends) if planned_ends else None
	actual_start_date = min(actual_starts) if actual_starts else None
	# "only when every child has one set" — not merely when at least one does.
	actual_end_date = max(actual_ends) if len(actual_ends) == len(children) else None

	percent_complete = sum(flt(child.percent_complete) for child in children) / len(children)

	return {
		"percent_complete": percent_complete,
		"planned_start_date": planned_start_date,
		"planned_end_date": planned_end_date,
		"actual_start_date": actual_start_date,
		"actual_end_date": actual_end_date,
		"duration_days": _duration(planned_start_date, planned_end_date),
		"status": _rollup_status(children),
	}


def refresh_activity_rollup(activity: str) -> None:
	"""Recompute `activity`'s rollup fields from its direct children only. No-op if not a group.

	A group with no children yet keeps whatever values it currently holds rather than being
	reset to blank/zero — there is nothing to derive from until it has at least one child.
	"""
	is_group = frappe.db.get_value("EGC Activity", activity, "is_group")
	if not is_group:
		return

	children = frappe.get_all(
		"EGC Activity",
		filters={"parent_egc_activity": activity},
		fields=list(_CHILD_FIELDS),
	)
	if not children:
		return

	_engine_set(activity, _compute_rollup(children))


def refresh_ancestors(activity: str | None) -> None:
	"""Walk `parent_egc_activity` upward from `activity`, refreshing each level bottom-up.

	Bottom-up is what makes a grandparent's rollup correct in a single pass: by the time its
	turn comes, the level below it (already visited this call) holds freshly recomputed values,
	not stale ones. Called from `EGC Activity`'s own `on_update`/`on_trash` with the *current*
	`parent_egc_activity`, so inserting, editing or deleting any Activity keeps its whole
	ancestor chain honest.
	"""
	current = activity
	while current:
		refresh_activity_rollup(current)
		current = frappe.db.get_value("EGC Activity", current, "parent_egc_activity")
