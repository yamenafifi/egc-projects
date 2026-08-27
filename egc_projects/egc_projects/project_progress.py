"""`Project.percent_complete` sync from EGC Activity roots.

Core `Project.update_percent_complete()` (`erpnext.projects.doctype.project.project`) runs on
EVERY `Project.save()` via `validate()`. With `percent_complete_method="Task Completion"` (the
field's own default) and zero core `Task` rows — this app uses `EGC Activity` exclusively, never
`Task` — core's own logic unconditionally sets `percent_complete = 0`, including via ERPNext's
own daily `update_project_sales_billing` scheduled job, which resaves every non-cancelled
Project. A one-time `frappe.db.set_value` fix would not survive the next save.

The fix is a SECOND `doc_events["Project"]["validate"]` hook (see `hooks.py`), appended after
`project_custom_fields.validate_project`. Frappe dispatches a doctype's own controller
`validate()` (core's own, which does the zero-reset) BEFORE hooks-registered `validate` handlers
for the same event, so this is guaranteed to run after core's reset on every save, not just once.
"""

from __future__ import annotations

import frappe
from frappe.utils import flt

#: A 5th option added to core `Project.percent_complete_method` via Property Setter
#: (`install.py`) — kept distinct from "Task Completion" so a project genuinely using core
#: `Task` is never silently reinterpreted, and so `_should_sync` can tell "nobody has decided
#: yet" (Task Completion, the field's own default, zero Tasks) from "this project explicitly
#: opted into Activity-driven progress."
PERCENT_COMPLETE_METHOD = "Activity Completion"

#: Matches the real `Project.status` Select options exactly ("On hold", lowercase "h") — this is
#: the same set core's own `update_percent_complete()` treats as untouchable.
_UNTOUCHED_STATUSES = ("Cancelled", "On hold")


def _should_sync(project: str, percent_complete_method: str | None) -> bool:
	if percent_complete_method == PERCENT_COMPLETE_METHOD:
		return True
	if percent_complete_method == "Task Completion":
		# Safe default: never override a project genuinely using core Task — if it has any
		# Task rows, core's own update_percent_complete() (which ran just before this hook,
		# same validate()) already computed a meaningful value from them this same save.
		has_tasks = frappe.db.exists("Task", {"project": project})
		has_activities = frappe.db.exists("EGC Activity", {"project": project})
		return not has_tasks and bool(has_activities)
	return False


def compute_percent_complete(project: str) -> float | None:
	"""Unweighted mean of ROOT EGC Activities' own (already-recursive, already weight-aware)
	percent_complete.

	A root's stored percent_complete is already a correct, fully-recursive rollup — computed
	bottom-up by `activity_control.refresh_activity_rollup()`/`refresh_ancestors()`, weighted by
	each level's own `weight_pct` where set — so this reads it directly, exactly like
	`_compute_rollup()` does one level up. Multiple roots are combined with an unweighted mean
	(weight is a within-one-parent allocation concept; nothing establishes a relative weight
	between a project's own top-level phases). `None` (not 0) if the project has no root
	Activities yet — nothing to derive from, matching `refresh_activity_rollup()`'s own "empty
	group keeps its current value" rule.
	"""
	roots = frappe.get_all(
		"EGC Activity",
		filters={"project": project, "parent_egc_activity": ("in", ("", None))},
		fields=["percent_complete"],
	)
	if not roots:
		return None
	return flt(sum(flt(r.percent_complete) for r in roots) / len(roots), 2)


def sync_project_percent_complete(doc, method=None) -> None:
	"""`doc_events["Project"]["validate"]` hook. Mutates `doc` in place; the framework persists
	it as part of the same save — no separate write here."""
	if not _should_sync(doc.name, doc.percent_complete_method):
		return
	value = compute_percent_complete(doc.name)
	if value is None:
		return
	doc.percent_complete = value
	if doc.status not in _UNTOUCHED_STATUSES:
		doc.status = "Completed" if value == 100 else "Open"


def refresh_project_percent_complete(project: str) -> None:
	"""Lightweight reactive refresh, called from `EGC Activity`'s own save/trash chain once
	`activity_control.refresh_ancestors()` reaches an actual root — so the Hub's Overview
	progress bar reflects an Activity edit immediately, not only on the next unrelated
	`Project.save()`. Uses `frappe.db.set_value` (no controller hooks, no full `Project.save()`
	round-trip, which would also re-run `update_costing()`/`update_sales_amount()`/etc —
	unrelated and wasteful on every Activity edit)."""
	method = frappe.db.get_value("Project", project, "percent_complete_method")
	if not _should_sync(project, method):
		return
	value = compute_percent_complete(project)
	if value is None:
		return
	values = {"percent_complete": value}
	status = frappe.db.get_value("Project", project, "status")
	if status not in _UNTOUCHED_STATUSES:
		values["status"] = "Completed" if value == 100 else "Open"
	frappe.db.set_value("Project", project, values, update_modified=False)
