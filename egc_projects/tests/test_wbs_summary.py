"""Tests for the WBS operational upgrade: `api/wbs.py`'s `get_wbs_summary`, `reorder_wbs_nodes`,
`copy_wbs_branch` and `bulk_create_wbs_nodes`.

Fixture style matches `test_wbs.py`: `make_test_project`/`make_wbs_node` build real records via
`.insert()` so every DocType validation actually runs. `_get_or_create_user` mirrors
`test_hub_api.py`'s additive-roles pattern for the permission tests.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from egc_projects.api import wbs
from egc_projects.egc_projects import constants as c


def get_or_create_test_company() -> str:
	existing = frappe.db.get_value("Company", {}, "name")
	if existing:
		return existing
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "_Test WBS Summary Company",
			"abbr": "TWSC",
			"default_currency": "USD",
			"country": "United Arab Emirates",
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def make_project(company: str, suffix: str) -> str:
	project = frappe.get_doc(
		{"doctype": "Project", "project_name": f"_Test WBS Summary {suffix}", "company": company, "status": "Open"}
	)
	project.insert(ignore_permissions=True)
	return project.name


def make_wbs_node(project: str, wbs_code: str, **kwargs) -> "frappe.Document":
	doc = frappe.get_doc(
		{"doctype": "EGC WBS Node", "project": project, "wbs_code": wbs_code, "wbs_name": kwargs.pop("wbs_name", wbs_code), **kwargs}
	)
	doc.insert(ignore_permissions=True)
	return doc


def make_activity(project: str, code: str, **kwargs) -> "frappe.Document":
	doc = frappe.get_doc(
		{"doctype": "EGC Activity", "project": project, "activity_code": code, "activity_name": code, **kwargs}
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


class TestWbsSummary(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = get_or_create_test_company()
		cls.manager_user = _get_or_create_user("egc-wbs-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER])

	def setUp(self):
		suffix = frappe.generate_hash(length=6)
		self.project = make_project(self.company, suffix)
		self.other_project = make_project(self.company, f"{suffix}-other")

	def tearDown(self):
		frappe.set_user("Administrator")

	def _build_tree(self):
		"""Mechanical (group) > HVAC (group) — Activities tagged at both levels."""
		mechanical = make_wbs_node(self.project, "MECH", is_group=1)
		hvac = make_wbs_node(self.project, "MECH-HVAC", parent_egc_wbs_node=mechanical.name, is_group=1)
		return mechanical, hvac

	# -- get_wbs_summary rollups -----------------------------------------------------------------

	def test_summary_aggregates_across_whole_subtree(self):
		mechanical, hvac = self._build_tree()
		make_activity(
			self.project,
			"A1",
			wbs_node=hvac.name,
			status="Completed",
			percent_complete=100,
			planned_start_date=today(),
			planned_end_date=add_days(today(), 5),
		)
		make_activity(
			self.project,
			"A2",
			wbs_node=hvac.name,
			status="In Progress",
			percent_complete=20,
			planned_end_date=add_days(today(), -3),  # overdue
		)
		# Tagged directly on Mechanical (not HVAC) — must ALSO roll up to Mechanical, proving a
		# node's own directly-tagged records count too, not only descendants'.
		make_activity(self.project, "A3", wbs_node=mechanical.name, status="Not Started", percent_complete=0)

		summary = {row["name"]: row for row in wbs.get_wbs_summary(self.project)}

		# HVAC: 2 activities, 1 completed, 1 overdue, average (100+20)/2 = 60.
		self.assertEqual(summary[hvac.name]["activity_total"], 2)
		self.assertEqual(summary[hvac.name]["activity_completed"], 1)
		self.assertEqual(summary[hvac.name]["activity_overdue_count"], 1)
		self.assertEqual(summary[hvac.name]["activity_progress"], 60)

		# Mechanical (the grandparent-of-none-here, direct parent of HVAC): must include BOTH
		# HVAC's subtree (2) AND its own directly-tagged A3 (1) = 3 total, not just 1.
		self.assertEqual(summary[mechanical.name]["activity_total"], 3)
		self.assertEqual(summary[mechanical.name]["activity_completed"], 1)

	def test_summary_drawing_and_submittal_counts(self):
		mechanical, hvac = self._build_tree()

		frappe.get_doc(
			{
				"doctype": "EGC Project Document",
				"project": self.project,
				"document_number": "DWG-WBS-1",
				"title": "Test Drawing",
				"document_type": "Drawing",
				"wbs_node": hvac.name,
			}
		).insert(ignore_permissions=True)
		# A non-drawing document (Specification) — must count toward document_count, but NOT
		# toward drawing_count, proving the two are genuinely distinct rollups, not the same
		# number under two names.
		frappe.get_doc(
			{
				"doctype": "EGC Project Document",
				"project": self.project,
				"document_number": "SPEC-WBS-1",
				"title": "Test Specification",
				"document_type": "Specification",
				"wbs_node": hvac.name,
			}
		).insert(ignore_permissions=True)

		submittal = frappe.get_doc(
			{
				"doctype": "EGC Submittal",
				"project": self.project,
				"submittal_number": "SUB-WBS-1",
				"title": "Test Submittal",
				"submittal_type": "Shop Drawing",
				"wbs_node": hvac.name,
			}
		).insert(ignore_permissions=True)
		# submittal_status defaults to Draft on insert (no submission yet) — force it to an
		# "open" state directly to isolate this test from the submittal engine's own lifecycle.
		frappe.db.set_value("EGC Submittal", submittal.name, "submittal_status", "Under Review")

		summary = {row["name"]: row for row in wbs.get_wbs_summary(self.project)}
		self.assertEqual(summary[hvac.name]["drawing_count"], 1)
		self.assertEqual(summary[mechanical.name]["drawing_count"], 1)  # rolled up
		self.assertEqual(summary[hvac.name]["document_count"], 2)
		self.assertEqual(summary[mechanical.name]["document_count"], 2)  # rolled up
		self.assertEqual(summary[hvac.name]["submittal_open_count"], 1)

	# -- reorder_wbs_nodes ------------------------------------------------------------------------

	def test_reorder_accepts_json_string_ordered_names(self):
		"""Regression: a real browser call sends list/dict arguments as a JSON-encoded string,
		not a Python list — Frappe v16's whitelist argument-type validation
		(frappe.utils.typing_validations) validates with Pydantic's `validate_python`, not
		`validate_json`, so a `list[str]` annotation on `ordered_names` would 500 on every real
		call even though a direct Python-list call (every other test in this file) works fine.
		Reproduced live via the Bulk Add dialog before this was caught; `reorder_wbs_nodes` and
		`bulk_create_wbs_nodes` are deliberately untyped for this parameter and parse a string
		themselves — this test is what stops that fix from silently regressing.
		"""
		import json

		mechanical, hvac = self._build_tree()
		a = make_wbs_node(self.project, "MECH-JSON-A", parent_egc_wbs_node=mechanical.name)
		wbs.reorder_wbs_nodes(mechanical.name, json.dumps([a.name, hvac.name]))
		self.assertEqual(frappe.db.get_value("EGC WBS Node", a.name, "sequence"), 0)
		self.assertEqual(frappe.db.get_value("EGC WBS Node", hvac.name, "sequence"), 1)

	def test_reorder_updates_sequence(self):
		mechanical, hvac = self._build_tree()
		a = make_wbs_node(self.project, "MECH-A", parent_egc_wbs_node=mechanical.name)
		b = make_wbs_node(self.project, "MECH-B", parent_egc_wbs_node=mechanical.name)

		wbs.reorder_wbs_nodes(mechanical.name, [b.name, hvac.name, a.name])
		self.assertEqual(frappe.db.get_value("EGC WBS Node", b.name, "sequence"), 0)
		self.assertEqual(frappe.db.get_value("EGC WBS Node", hvac.name, "sequence"), 1)
		self.assertEqual(frappe.db.get_value("EGC WBS Node", a.name, "sequence"), 2)

	def test_reorder_rejects_node_not_under_given_parent(self):
		mechanical, hvac = self._build_tree()
		other_root = make_wbs_node(self.project, "ELEC")
		with self.assertRaises(frappe.ValidationError):
			wbs.reorder_wbs_nodes(mechanical.name, [hvac.name, other_root.name])

	# -- copy_wbs_branch --------------------------------------------------------------------------

	def test_copy_branch_deep_copies_and_avoids_code_collision(self):
		mechanical, hvac = self._build_tree()
		leaf = make_wbs_node(self.project, "MECH-HVAC-DUCT", parent_egc_wbs_node=hvac.name)

		copy_name = wbs.copy_wbs_branch(mechanical.name, target_parent=None)
		copy_doc = frappe.get_doc("EGC WBS Node", copy_name)
		self.assertNotEqual(copy_doc.wbs_code, mechanical.wbs_code)
		self.assertTrue(copy_doc.wbs_code.startswith("MECH"))

		copy_children = frappe.get_all("EGC WBS Node", filters={"parent_egc_wbs_node": copy_name}, pluck="name")
		self.assertEqual(len(copy_children), 1)
		copy_grandchildren = frappe.get_all(
			"EGC WBS Node", filters={"parent_egc_wbs_node": copy_children[0]}, pluck="name"
		)
		self.assertEqual(len(copy_grandchildren), 1)

	def test_copy_branch_across_projects_sets_target_project_on_every_node(self):
		mechanical, hvac = self._build_tree()
		make_wbs_node(self.project, "MECH-HVAC-DUCT2", parent_egc_wbs_node=hvac.name)

		copy_name = wbs.copy_wbs_branch(mechanical.name, target_parent=None, project=self.other_project)

		def assert_project_recursive(name):
			doc = frappe.get_doc("EGC WBS Node", name)
			self.assertEqual(doc.project, self.other_project)
			for child in frappe.get_all("EGC WBS Node", filters={"parent_egc_wbs_node": name}, pluck="name"):
				assert_project_recursive(child)

		assert_project_recursive(copy_name)

	# -- bulk_create_wbs_nodes --------------------------------------------------------------------

	def test_bulk_create_accepts_json_string_rows(self):
		"""Same regression as test_reorder_accepts_json_string_ordered_names, for `rows`."""
		import json

		names = wbs.bulk_create_wbs_nodes(
			None, self.project, json.dumps([{"wbs_code": "BULK-JSON", "wbs_name": "JSON Row"}])
		)
		self.assertEqual(len(names), 1)
		self.assertTrue(frappe.db.exists("EGC WBS Node", names[0]))

	def test_bulk_create_happy_path(self):
		names = wbs.bulk_create_wbs_nodes(
			None,
			self.project,
			[
				{"wbs_code": "BULK-A", "wbs_name": "A"},
				{"wbs_code": "BULK-B", "wbs_name": "B", "is_group": 1},
			],
		)
		self.assertEqual(len(names), 2)
		self.assertTrue(frappe.db.exists("EGC WBS Node", names[0]))
		self.assertTrue(frappe.db.exists("EGC WBS Node", names[1]))

	def test_bulk_create_aborts_whole_batch_on_invalid_row(self):
		make_wbs_node(self.project, "BULK-DUP")
		with self.assertRaises(frappe.DuplicateEntryError):
			wbs.bulk_create_wbs_nodes(
				None,
				self.project,
				[{"wbs_code": "BULK-OK", "wbs_name": "OK"}, {"wbs_code": "BULK-DUP", "wbs_name": "Duplicate"}],
			)
		self.assertFalse(frappe.db.exists("EGC WBS Node", {"project": self.project, "wbs_code": "BULK-OK"}))

	# -- project isolation ------------------------------------------------------------------------

	def test_endpoints_reject_project_isolation_breach(self):
		mechanical, hvac = self._build_tree()

		fenced_user = _get_or_create_user("egc-wbs-fenced@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER])
		frappe.get_doc(
			{"doctype": "User Permission", "user": fenced_user, "allow": "Project", "for_value": self.other_project}
		).insert(ignore_permissions=True)

		frappe.set_user(fenced_user)
		with self.assertRaises(frappe.PermissionError):
			wbs.get_wbs_summary(self.project)
		with self.assertRaises(frappe.PermissionError):
			wbs.reorder_wbs_nodes(mechanical.name, [hvac.name])
		with self.assertRaises(frappe.PermissionError):
			wbs.bulk_create_wbs_nodes(None, self.project, [{"wbs_code": "X", "wbs_name": "X"}])
