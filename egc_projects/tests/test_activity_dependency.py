"""Tests for `EGC Activity Dependency` and the `api/activities.py` endpoints that sit on top of
Activities/Dependencies (docs/ARCHITECTURE_V2.md §6, §12).

Fixture style matches `test_activity.py`/`test_hub_api.py`: dedicated `Project` fixtures, and a
`_make_user` helper for the additive-roles permission tests (an EGC role alone does not grant
anything on core `Project` — a test user also needs `Projects User`).
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from egc_projects.api import activities
from egc_projects.egc_projects import constants as c


def get_test_company() -> str:
	existing = frappe.db.get_value("Company", {}, "name")
	if existing:
		return existing
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "EGC Activity Dependency Test Co",
			"abbr": "EADC",
			"default_currency": "USD",
			"country": "United Arab Emirates",
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def make_project(project_name: str) -> str:
	project = frappe.get_doc(
		{"doctype": "Project", "project_name": project_name, "company": get_test_company(), "status": "Open"}
	)
	project.insert(ignore_permissions=True)
	return project.name


def make_activity(project, activity_code, activity_name, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "EGC Activity",
			"project": project,
			"activity_code": activity_code,
			"activity_name": activity_name,
			**kwargs,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def make_dependency(predecessor, successor, **kwargs):
	doc = frappe.get_doc(
		{
			"doctype": "EGC Activity Dependency",
			"predecessor": predecessor,
			"successor": successor,
			**kwargs,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _get_or_create_user(email, roles):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user.set("roles", [])
	for role in roles:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return user.name


class TestActivityDependency(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.manager_user = _get_or_create_user(
			"egc-ad-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)

	def setUp(self):
		suffix = frappe.generate_hash(length=6)
		self.project = make_project(f"EGC Activity Dependency Test {suffix}")
		self.other_project = make_project(f"EGC Activity Dependency Other {suffix}")

	def tearDown(self):
		frappe.set_user("Administrator")

	# -- doctype-level validation ----------------------------------------------------------------

	def test_same_project_dependency_accepted(self):
		a = make_activity(self.project, "DEP-A", "A")
		b = make_activity(self.project, "DEP-B", "B")
		dep = make_dependency(a.name, b.name)
		self.assertEqual(dep.project, self.project)

	def test_cross_project_dependency_rejected(self):
		a = make_activity(self.project, "DEP-A2", "A")
		b = make_activity(self.other_project, "DEP-B2", "B")
		with self.assertRaises(frappe.ValidationError):
			make_dependency(a.name, b.name)

	def test_self_dependency_rejected(self):
		a = make_activity(self.project, "DEP-SELF", "A")
		with self.assertRaises(frappe.ValidationError):
			make_dependency(a.name, a.name)

	def test_duplicate_pair_rejected(self):
		a = make_activity(self.project, "DEP-DUP-A", "A")
		b = make_activity(self.project, "DEP-DUP-B", "B")
		make_dependency(a.name, b.name)
		with self.assertRaises(frappe.DuplicateEntryError):
			make_dependency(a.name, b.name)

	def test_three_node_cycle_rejected(self):
		a = make_activity(self.project, "CYC-A", "A")
		b = make_activity(self.project, "CYC-B", "B")
		c_ = make_activity(self.project, "CYC-C", "C")
		make_dependency(a.name, b.name)
		make_dependency(b.name, c_.name)
		with self.assertRaises(frappe.ValidationError):
			make_dependency(c_.name, a.name)

	def test_valid_chain_without_cycle_accepted(self):
		a = make_activity(self.project, "CHAIN-A", "A")
		b = make_activity(self.project, "CHAIN-B", "B")
		c_ = make_activity(self.project, "CHAIN-C", "C")
		make_dependency(a.name, b.name)
		make_dependency(b.name, c_.name)  # no cycle: A->B->C is a straight chain

	# -- api/activities.py -----------------------------------------------------------------------

	def test_get_activity_gantt_rows_shape(self):
		a = make_activity(self.project, "GANTT-A", "A", is_milestone=1)
		b = make_activity(self.project, "GANTT-B", "B")
		make_dependency(a.name, b.name)

		rows = activities.get_activity_gantt_rows(self.project)
		by_id = {row["id"]: row for row in rows}
		self.assertIn(a.name, by_id)
		self.assertIn(b.name, by_id)
		self.assertIn(a.name, by_id[b.name]["dependencies"].split(","))
		self.assertIn("egc-gantt-milestone", by_id[a.name]["custom_class"] or "")

	def test_update_activity_progress_rejects_group(self):
		group = make_activity(self.project, "PROG-GRP", "Group", is_group=1)
		with self.assertRaises(frappe.ValidationError):
			activities.update_activity_progress(group.name, 50)

	def test_update_activity_progress_updates_leaf(self):
		leaf = make_activity(self.project, "PROG-LEAF", "Leaf")
		result = activities.update_activity_progress(leaf.name, 75, status=c.ACTIVITY_IN_PROGRESS)
		self.assertEqual(result["percent_complete"], 75)
		self.assertEqual(result["status"], c.ACTIVITY_IN_PROGRESS)

	# -- create_child_activity -------------------------------------------------------------------

	def test_create_child_activity_turns_a_leaf_parent_into_a_group(self):
		"""Regression: every Hub "Add Child Activity" dialog promised this ("Adding a child will
		make this a group activity") but went through a bare `frappe.client.insert`, which
		`validators.validate_tree_parent` always rejected on a non-group parent — so the button
		never actually worked on a fresh leaf Activity."""
		leaf = make_activity(self.project, "CHILD-PARENT", "Parent", percent_complete=40)
		self.assertFalse(leaf.is_group)

		frappe.set_user(self.manager_user)
		child = activities.create_child_activity(leaf.name, activity_code="CHILD-KID", activity_name="Kid")

		leaf.reload()
		self.assertTrue(leaf.is_group)
		self.assertEqual(child["activity_code"], "CHILD-KID")
		self.assertEqual(child["parent_egc_activity"], leaf.name)
		# The parent's stale hand-entered percent_complete must be corrected by the rollup engine
		# once it's a real group with a real child, not left at its old leaf-era value.
		self.assertEqual(leaf.percent_complete, 0)

	def test_create_child_activity_on_an_existing_group_leaves_it_alone(self):
		group = make_activity(self.project, "CHILD-GRP", "Group", is_group=1)
		frappe.set_user(self.manager_user)
		activities.create_child_activity(group.name, activity_code="CHILD-GRP-KID", activity_name="Kid")
		group.reload()
		self.assertTrue(group.is_group)

	def test_create_child_activity_requires_activity_code_and_name(self):
		leaf = make_activity(self.project, "CHILD-BLANK", "Parent")
		frappe.set_user(self.manager_user)
		with self.assertRaises(frappe.ValidationError):
			activities.create_child_activity(leaf.name, activity_name="Kid")

	def test_get_activity_detail_includes_dependencies_and_links(self):
		a = make_activity(self.project, "DETAIL-A", "A")
		b = make_activity(self.project, "DETAIL-B", "B")
		make_dependency(a.name, b.name, dependency_type=c.DEPENDENCY_SS, lag_days=2)

		detail = activities.get_activity_detail(b.name)
		self.assertEqual(len(detail["dependencies"]["predecessors"]), 1)
		self.assertEqual(detail["dependencies"]["predecessors"][0]["activity"], a.name)
		self.assertEqual(detail["dependencies"]["predecessors"][0]["dependency_type"], c.DEPENDENCY_SS)
		self.assertEqual(detail["dependencies"]["predecessors"][0]["lag_days"], 2)
		self.assertIn("links", detail)

	def test_add_and_remove_dependency_endpoints(self):
		a = make_activity(self.project, "RT-A", "A")
		b = make_activity(self.project, "RT-B", "B")
		frappe.set_user(self.manager_user)
		name = activities.add_dependency(a.name, b.name, c.DEPENDENCY_FF, 3)
		self.assertTrue(frappe.db.exists("EGC Activity Dependency", name))
		activities.remove_dependency(name)
		self.assertFalse(frappe.db.exists("EGC Activity Dependency", name))

	def test_get_activity_detail_includes_is_overdue(self):
		overdue = make_activity(
			self.project, "OD-A", "Overdue", planned_end_date=add_days(today(), -3), status=c.ACTIVITY_NOT_STARTED
		)
		on_track = make_activity(
			self.project, "OD-B", "On Track", planned_end_date=add_days(today(), 3), status=c.ACTIVITY_NOT_STARTED
		)
		self.assertTrue(activities.get_activity_detail(overdue.name)["activity"]["is_overdue"])
		self.assertFalse(activities.get_activity_detail(on_track.name)["activity"]["is_overdue"])

	def test_get_activity_history_empty_for_freshly_created_activity(self):
		leaf = make_activity(self.project, "HIST-NEW", "Fresh")
		self.assertEqual(activities.get_activity_history(leaf.name), [])

	def test_get_activity_history_tracks_progress_and_status_changes(self):
		leaf = make_activity(self.project, "HIST-A", "Leaf")
		activities.update_activity_progress(leaf.name, 40, status=c.ACTIVITY_IN_PROGRESS)
		activities.update_activity_progress(leaf.name, 80)

		events = activities.get_activity_history(leaf.name)
		self.assertEqual(len(events), 2)

		first_fields = {change["field"] for change in events[0]["changes"]}
		self.assertIn("percent_complete", first_fields)
		self.assertIn("status", first_fields)
		first_progress = next(ch for ch in events[0]["changes"] if ch["field"] == "percent_complete")
		self.assertEqual(first_progress["to"], "40.0%")  # get_diff formats Percent fields as text

		second_fields = {change["field"] for change in events[1]["changes"]}
		self.assertIn("percent_complete", second_fields)
		self.assertNotIn("status", second_fields)  # unchanged on the second call, so no diff row for it

	# -- project isolation ------------------------------------------------------------------------

	def test_endpoints_reject_project_isolation_breach(self):
		a = make_activity(self.project, "ISO-A", "A")
		b = make_activity(self.project, "ISO-B", "B")
		make_dependency(a.name, b.name)

		fenced_user = _get_or_create_user("egc-ad-fenced@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER])
		frappe.get_doc(
			{"doctype": "User Permission", "user": fenced_user, "allow": "Project", "for_value": self.other_project}
		).insert(ignore_permissions=True)

		frappe.set_user(fenced_user)
		with self.assertRaises(frappe.PermissionError):
			activities.get_activity_detail(a.name)
		with self.assertRaises(frappe.PermissionError):
			activities.get_activity_gantt_rows(self.project)
		with self.assertRaises(frappe.PermissionError):
			activities.add_dependency(a.name, b.name)
