# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""`EGC Activity Dependency` — recorded, validated predecessor/successor links between two
Activities of the same project (docs/ARCHITECTURE_V2.md §6).

Used to deliberately NOT drive automatic forecast-date shifting — reversed by Level 0 §27-§28,
which wants exactly that for FORECAST dates (never Baseline, never Actual). The actual push lives
in `schedule_engine.py`; `after_insert`/`on_update` below just call it whenever a dependency is
created or its type/lag changes, since either can immediately put the successor's current
forecast in violation of a constraint that didn't exist (or was weaker) a moment ago. No critical-
path calculation is added by this — still out of scope, per §6.

`project` is `fetch_from: predecessor.project` in the JSON, which the framework populates before
`validate()` runs (`Document._validate_links()` fires ahead of the `validate` hook on both insert
and update), so it is always the predecessor's project by the time any check below reads it —
the "anchor" the successor is validated against, per the work package spec.

No composite unique DB index is declared in the JSON, for the same reason as `EGC Activity Link`
(docs/ARCHITECTURE.md §2.6): Frappe v16's DocType schema has no multi-column `unique` key, so the
(`predecessor`, `successor`) rule is enforced in `validate()`. Because this DocType is hash-named,
`on_doctype_update()` below backs that application-level check with a real DB constraint, closing
the same concurrent-insert race `EGC Activity Link` was found to have.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from egc_projects.egc_projects import schedule_engine
from egc_projects.egc_projects.validators import validate_same_project


class EGCActivityDependency(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		dependency_type: DF.Literal["Finish-to-Start", "Start-to-Start", "Finish-to-Finish", "Start-to-Finish"]
		lag_days: DF.Int
		predecessor: DF.Link
		project: DF.Link
		successor: DF.Link
	# end: auto-generated types

	def validate(self):
		self.validate_not_self_dependency()
		validate_same_project(self, "successor", "EGC Activity", "Successor")
		self.validate_no_duplicate_pair()
		self.validate_no_cycle()

	def after_insert(self):
		schedule_engine.propagate_from(self.predecessor)

	def on_update(self):
		if self.has_value_changed("dependency_type") or self.has_value_changed("lag_days"):
			schedule_engine.propagate_from(self.predecessor)

	def validate_not_self_dependency(self):
		if self.predecessor and self.predecessor == self.successor:
			frappe.throw(
				_("An Activity cannot depend on itself."),
				title=_("Invalid Dependency"),
				exc=frappe.ValidationError,
			)

	def validate_no_duplicate_pair(self):
		existing = frappe.db.get_value(
			"EGC Activity Dependency",
			{
				"predecessor": self.predecessor,
				"successor": self.successor,
				"name": ("!=", self.name or ""),
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("A dependency from {0} to {1} already exists ({2}).").format(
					frappe.bold(self.predecessor), frappe.bold(self.successor), existing
				),
				title=_("Duplicate Dependency"),
				exc=frappe.DuplicateEntryError,
			)

	def validate_no_cycle(self):
		# The new edge is predecessor -> successor. It closes a cycle exactly when `predecessor`
		# is already reachable by walking forward from `successor` over the EXISTING edges of
		# this project — i.e. the successor, directly or transitively, already leads back to the
		# activity that is about to depend on it.
		if _reaches(self.successor, self.predecessor, self.project, exclude=self.name):
			frappe.throw(
				_(
					"This dependency would create a cycle: {0} already leads (directly or"
					" indirectly) back to {1}."
				).format(frappe.bold(self.successor), frappe.bold(self.predecessor)),
				title=_("Circular Dependency"),
				exc=frappe.ValidationError,
			)


def _reaches(start: str, target: str, project: str, exclude: str | None = None) -> bool:
	"""Plain BFS over this project's existing dependency edges: can `start` reach `target`?

	Project-scoped Activity graphs are small (a handful to a few hundred nodes), so one query to
	load every edge and an in-memory walk is deliberately simpler than anything graph-database-ish
	(docs/ARCHITECTURE_V2.md §6).
	"""
	edges = frappe.get_all(
		"EGC Activity Dependency",
		filters={"project": project, "name": ("!=", exclude or "")},
		fields=["predecessor", "successor"],
	)
	graph: dict[str, list[str]] = {}
	for edge in edges:
		graph.setdefault(edge.predecessor, []).append(edge.successor)

	visited: set[str] = set()
	queue = [start]
	while queue:
		node = queue.pop(0)
		if node == target:
			return True
		if node in visited:
			continue
		visited.add(node)
		queue.extend(graph.get(node, []))
	return False


def on_doctype_update():
	# See module docstring: this DocType is hash-named, so nothing in its primary key stops two
	# concurrent inserts from racing past the `validate()`-time duplicate-pair check.
	frappe.db.add_unique(
		"EGC Activity Dependency",
		["predecessor", "successor"],
		constraint_name="unique_activity_dependency_pair",
	)
