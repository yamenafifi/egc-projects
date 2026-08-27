"""Dependency-driven forecast-date propagation (Level 0 §27-§28).

This reverses an explicit boundary stated elsewhere in this app (`egc_activity_dependency.py`'s
own docstring: "Deliberately does not drive automatic forecast-date shifting... A dependency is
recorded and validated only"). Level 0 §27-§28 is the newer, governing instruction and wants the
opposite for FORECAST dates specifically — Baseline (`planned_start_date`/`planned_end_date`) and
Actual dates stay exactly what they always were: the user's own record, never touched here.

Two halves, mirroring the guard+engine split already used elsewhere in this app
(`activity_control.py`'s rollup fields, `document_control.py`'s engine-authorized fields):

1. `assert_dependency_constraints_satisfied` (called from `EGC Activity.validate()`) rejects a
   DIRECT hand-edit of `forecast_start_date`/`forecast_end_date` that would violate an existing
   dependency's minimum — same discipline as every other validation in this app: reject invalid
   state, never silently coerce a value the user just typed.
2. `propagate_from` (called after a predecessor's own dates change, and whenever a dependency is
   added) walks that predecessor's direct successors and pushes each one's forecast dates FORWARD
   just enough to satisfy the dependency — never pulls a successor's forecast earlier, and never
   overrides a forecast that already satisfies the constraint (a PM's own later, more informed
   forecast is left alone). Writes go through `frappe.db.set_value`, bypassing `validate()`
   entirely, exactly like `activity_control._engine_set` — so this can never re-trigger #1 above
   on its own writes, and cascades safely to further successors (recursion terminates because
   `EGC Activity Dependency.validate()` already rejects any edge that would create a cycle).

This is one-directional constraint propagation, not a full CPM engine: no backward float, no
critical-path calculation — still explicitly out of scope (docs/ARCHITECTURE_V2.md §6).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, date_diff, getdate

from egc_projects.egc_projects import constants as c

ENGINE_FLAG = "egc_schedule_engine"

_DATE_FIELDS = (
	"name",
	"planned_start_date",
	"planned_end_date",
	"forecast_start_date",
	"forecast_end_date",
	"actual_start_date",
	"actual_end_date",
	"duration_days",
	"is_group",
)


def _effective_dates(row) -> tuple[str | None, str | None]:
	"""What this activity is ACTUALLY expected to run — actual dates once known, else the current
	forecast, else the baseline plan. Used both as "my own position" and as "my predecessor's
	position" (the same rule both ways: the best information available right now)."""
	start = row.actual_start_date or row.forecast_start_date or row.planned_start_date
	end = row.actual_end_date or row.forecast_end_date or row.planned_end_date
	return start, end


def _min_constraints(dependency_type: str, lag_days: int, pred_start, pred_end) -> tuple:
	"""The (min_start, min_end) a dependency's own type implies for the SUCCESSOR — either may be
	`None` when that dependency type doesn't constrain that end, or the predecessor doesn't yet
	have the date this type reads from."""
	lag = lag_days or 0
	if dependency_type == c.DEPENDENCY_FS:
		return (add_days(pred_end, lag + 1) if pred_end else None), None
	if dependency_type == c.DEPENDENCY_SS:
		return (add_days(pred_start, lag) if pred_start else None), None
	if dependency_type == c.DEPENDENCY_FF:
		return None, (add_days(pred_end, lag) if pred_end else None)
	if dependency_type == c.DEPENDENCY_SF:
		return None, (add_days(pred_start, lag) if pred_start else None)
	return None, None


def _activity_row(activity: str):
	rows = frappe.get_all("EGC Activity", filters={"name": activity}, fields=list(_DATE_FIELDS))
	return rows[0] if rows else None


def _violations_for(activity: str, own_start, own_end) -> list[dict]:
	"""The shared check, given the CALLER's choice of what "this activity's own dates" means —
	`get_dependency_violations` reads them fresh from the database, `assert_dependency_constraints_
	satisfied` reads them from the in-memory doc being validated (which, mid-`validate()`, may not
	be saved to the database yet — reading the DB there would check the OLD value, not the one
	actually being rejected or allowed)."""
	deps = frappe.get_all(
		"EGC Activity Dependency",
		filters={"successor": activity},
		fields=["name", "predecessor", "dependency_type", "lag_days"],
	)
	if not deps:
		return []

	pred_rows = {
		row.name: row
		for row in frappe.get_all(
			"EGC Activity", filters={"name": ("in", [d.predecessor for d in deps])}, fields=list(_DATE_FIELDS)
		)
	}

	violations = []
	for dep in deps:
		pred = pred_rows.get(dep.predecessor)
		if not pred:
			continue
		pred_start, pred_end = _effective_dates(pred)
		min_start, min_end = _min_constraints(dep.dependency_type, dep.lag_days, pred_start, pred_end)
		if min_start and own_start and getdate(own_start) < getdate(min_start):
			violations.append(
				{
					"dependency": dep.name,
					"predecessor": dep.predecessor,
					"dependency_type": dep.dependency_type,
					"field": "forecast_start_date",
					"minimum": min_start,
				}
			)
		if min_end and own_end and getdate(own_end) < getdate(min_end):
			violations.append(
				{
					"dependency": dep.name,
					"predecessor": dep.predecessor,
					"dependency_type": dep.dependency_type,
					"field": "forecast_end_date",
					"minimum": min_end,
				}
			)
	return violations


def get_dependency_violations(activity: str) -> list[dict]:
	"""Every predecessor dependency of `activity` whose minimum constraint the activity's own
	CURRENT (as stored in the database) effective dates fail to satisfy right now. Used by tests
	and an audit — never mutates anything. `assert_dependency_constraints_satisfied` below does
	NOT call this: it needs the in-memory doc's pending value, not what is already in the database."""
	own = _activity_row(activity)
	if not own:
		return []
	own_start, own_end = _effective_dates(own)
	return _violations_for(activity, own_start, own_end)


def assert_dependency_constraints_satisfied(doc) -> None:
	"""Guard half — wired into `EGC Activity.validate()`. Only fires when this activity's own
	forecast dates were just hand-edited (an engine-driven `propagate_from` write below never
	re-enters this: it goes through `frappe.db.set_value`, which never calls `validate()` at
	all) — a `propagate_from` correction can never trip its own guard. Checks the doc's own
	IN-MEMORY dates, not a fresh database read — `validate()` runs before the write lands, so the
	database still holds the old value at this point."""
	if doc.is_group or doc.is_new():
		return
	if not (doc.has_value_changed("forecast_start_date") or doc.has_value_changed("forecast_end_date")):
		return

	own_start, own_end = _effective_dates(doc)
	for violation in _violations_for(doc.name, own_start, own_end):
		frappe.throw(
			_(
				"{0} cannot start or finish before {1} allows ({2} dependency on {3},"
				" minimum {4})."
			).format(
				frappe.bold(doc.name),
				_(violation["field"].replace("_", " ").title()),
				_(violation["dependency_type"]),
				frappe.bold(violation["predecessor"]),
				frappe.format(violation["minimum"], {"fieldtype": "Date"}),
			),
			title=_("Dependency Violation"),
			exc=frappe.ValidationError,
		)


def propagate_from(activity: str, _visited: set[str] | None = None) -> None:
	"""Engine half — pushes every DIRECT successor of `activity` forward just enough to satisfy
	its dependency on `activity`, then recurses onto that successor's own successors so a change
	early in a chain reaches everything downstream. Call after any write that can change what
	`activity` itself effectively means for its successors: its own dates changing, or a new
	dependency being added where `activity` is the predecessor."""
	visited = _visited if _visited is not None else set()
	if activity in visited:
		return
	visited.add(activity)

	pred = _activity_row(activity)
	if not pred:
		return
	pred_start, pred_end = _effective_dates(pred)
	if not pred_start and not pred_end:
		return

	deps = frappe.get_all(
		"EGC Activity Dependency",
		filters={"predecessor": activity},
		fields=["successor", "dependency_type", "lag_days"],
	)
	for dep in deps:
		_push_successor(dep.successor, dep.dependency_type, dep.lag_days, pred_start, pred_end, visited)


def _push_successor(successor: str, dependency_type: str, lag_days: int, pred_start, pred_end, visited: set[str]) -> None:
	row = _activity_row(successor)
	if not row or row.is_group:
		# A group's dates are rollup-owned by activity_control.py, not by this engine — pushing
		# them here would just be immediately overwritten by the next rollup refresh anyway.
		return

	min_start, min_end = _min_constraints(dependency_type, lag_days, pred_start, pred_end)
	if not min_start and not min_end:
		return

	cur_start, cur_end = _effective_dates(row)
	# Only the fields actually pushed go in here — NOT the effective-date fallback for a field
	# this dependency never touches. Writing `cur_start`/`cur_end` unconditionally would silently
	# convert a planned-date FALLBACK into an explicit forecast value nothing asked to set.
	update: dict = {}

	if min_start and (not cur_start or getdate(min_start) > getdate(cur_start)):
		duration = date_diff(cur_end, cur_start) if cur_start and cur_end else max(row.duration_days or 0, 0)
		update["forecast_start_date"] = min_start
		if not min_end and duration > 0:
			# Only start is directly constrained (FS/SS) — preserve the activity's own known
			# duration by sliding its finish out by the same amount, rather than leaving a stale
			# finish before the new start or silently collapsing the duration to zero.
			update["forecast_end_date"] = add_days(min_start, duration)

	if min_end:
		# If the block above already computed a new finish (duration preservation), compare
		# against THAT, not the old one — an FS+FF pair on the same dependency should never lose
		# to a stale read.
		compare_end = update.get("forecast_end_date", cur_end)
		if not compare_end or getdate(min_end) > getdate(compare_end):
			update["forecast_end_date"] = min_end

	if not update:
		return

	frappe.flags[ENGINE_FLAG] = True
	try:
		frappe.db.set_value("EGC Activity", successor, update, update_modified=False)
	finally:
		frappe.flags[ENGINE_FLAG] = False

	propagate_from(successor, visited)
