# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for Project Information (ARCHITECTURE_V2.md §1/§2/§3/§4): `EGC Project Profile`, its
`stakeholders`/`equipment_items` child tables, `project_profile.py`'s stable
`resolve_role_user`/`get_stakeholders` contract, and `api/hub.py`'s `get_project_profile` /
`save_project_profile` / extended `get_project_context`.

Fixture style matches `test_document_control.py`/`test_hub_api.py`: one shared set of masters
in `setUpClass`, one dedicated `Project` per test in `setUp`. EGC roles are additive and grant
nothing on core `Project` (docs/ARCHITECTURE.md §4), so `viewer_user` is built with `Projects
User` as well as `EGC Project Viewer` — otherwise it would fail at the `Project` read gate
before ever reaching the `edit_profile` check this test suite is actually after.

`EGC Stakeholder Role`/`EGC Modality`/`EGC Equipment Manufacturer` are not seeded anywhere yet
(seeding them is a follow-up for `install.py`, lead-owned) — every fixture here is created
directly, per the work package's own instruction not to assume any master exists.
"""

import frappe
from frappe.tests import IntegrationTestCase

from egc_projects.api import hub
from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import project_profile


class TestProjectProfile(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]

		# "EGC Project Manager" and "Client" are two of the five names ARCHITECTURE_V2.md §4
		# hard-wires as `project_profile.KEY_STAKEHOLDER_ROLES` — used to exercise the
		# `get_project_context()["profile"]["key_stakeholders"]` filtering. "EGC Project
		# Manager" as an `EGC Stakeholder Role` master row is a distinct record from the
		# permission `Role` of the same name (different doctype entirely); the coincidence is
		# intentional per ARCHITECTURE_V2.md §2 (that stakeholder slot is usually filled by
		# whoever holds the matching Role).
		cls.role_pm = _get_or_create_stakeholder_role("EGC Project Manager", is_egc_internal=1)
		cls.role_client = _get_or_create_stakeholder_role("Client", is_egc_internal=0)
		# Deliberately NOT in KEY_STAKEHOLDER_ROLES, so it can prove both "role not present"
		# (resolve_role_user) and "present but filtered out of the header summary" (hub context).
		cls.role_other = _get_or_create_stakeholder_role("EGC-PP-Test Other Role", is_egc_internal=1)

		cls.manager_user = _get_or_create_user(
			"egc-pp-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		cls.viewer_user = _get_or_create_user(
			"egc-pp-viewer@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER]
		)

	def setUp(self):
		self.project = _make_project(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")

	# -- 1. Create via save_project_profile, then re-save updates the same row --------------

	def test_save_project_profile_creates_then_updates_same_row(self):
		frappe.set_user(self.manager_user)

		saved = hub.save_project_profile(self.project, {"project_code": "PC-001", "sector": "Healthcare"})
		self.assertEqual(saved["project"], self.project)
		self.assertEqual(saved["project_code"], "PC-001")
		self.assertEqual(saved["sector"], "Healthcare")
		self.assertEqual(frappe.db.exists("EGC Project Profile", self.project), self.project)
		self.assertEqual(frappe.db.count("EGC Project Profile", {"project": self.project}), 1)

		saved_again = hub.save_project_profile(self.project, {"project_code": "PC-002"})
		self.assertEqual(saved_again["project_code"], "PC-002")
		# The 1:1 constraint holds because of `field:project` autoname, not a second check —
		# still exactly one row, updated in place, not a second Profile for the same project.
		self.assertEqual(frappe.db.count("EGC Project Profile", {"project": self.project}), 1)

	# -- 1b. An untouched Select field must stay unset, never silently default to its first
	#         option (regression — see egc_project_profile.json's leading-blank-line fix) -----

	def test_untouched_select_fields_stay_empty(self):
		"""Frappe's `get_new_doc()` defaults a Select field with no explicit value to the FIRST
		line of its `options` string, unless that string begins with a blank line (see
		`frappe/model/create_new.py`). Every optional Select on this doctype
		(`project_stage`/`sector`/`delivery_method`/`contract_type`) must carry that leading
		blank line, or saving a profile that only sets one field silently corrupts every other
		Select field to whatever its first option happens to be — reproduced live: saving only
		`project_stage` also wrote `delivery_method="Design-Bid-Build"` and
		`contract_type="Lump Sum"` before this was fixed.
		"""
		frappe.set_user(self.manager_user)

		saved = hub.save_project_profile(self.project, {"project_stage": "Construction"})
		self.assertEqual(saved["project_stage"], "Construction")
		self.assertFalse(saved["sector"])
		self.assertFalse(saved["delivery_method"])
		self.assertFalse(saved["contract_type"])

		# The false-y check above would also pass for None; assert the exact on-disk value too,
		# since a Select field's "unset" representation is an empty string, not NULL.
		row = frappe.db.get_value(
			"EGC Project Profile", self.project, ["sector", "delivery_method", "contract_type"], as_dict=True
		)
		self.assertEqual(row.sector, "")
		self.assertEqual(row.delivery_method, "")
		self.assertEqual(row.contract_type, "")

	# -- 2. get_project_profile with no row returns a sane empty shape, not an exception -----

	def test_get_project_profile_no_row_returns_empty_shape(self):
		frappe.set_user(self.manager_user)

		result = hub.get_project_profile(self.project)
		self.assertEqual(result["project"], self.project)
		self.assertIsNone(result["project_code"])
		self.assertIsNone(result["sector"])
		self.assertEqual(result["stakeholders"], [])
		self.assertEqual(result["equipment_items"], [])

	# -- 3. Cross-project WBS node on an equipment item is rejected --------------------------

	def test_equipment_item_wbs_node_cross_project_rejected(self):
		other_project = _make_project(self.company)
		other_wbs = _make_wbs_node(other_project, "EQ-X")

		frappe.set_user(self.manager_user)
		with self.assertRaises(frappe.ValidationError):
			hub.save_project_profile(
				self.project,
				{"equipment_items": [{"facility": "Radiology", "wbs_node": other_wbs}]},
			)
		# Nothing was persisted — validate() runs before insert, so a rejected save leaves no
		# stray Profile row behind for this project.
		self.assertFalse(frappe.db.exists("EGC Project Profile", self.project))

	def test_equipment_item_wbs_node_same_project_accepted(self):
		wbs = _make_wbs_node(self.project, "EQ-OK")

		frappe.set_user(self.manager_user)
		saved = hub.save_project_profile(
			self.project,
			{"equipment_items": [{"facility": "Radiology", "modality": None, "wbs_node": wbs}]},
		)
		self.assertEqual(len(saved["equipment_items"]), 1)
		self.assertEqual(saved["equipment_items"][0]["wbs_node"], wbs)
		self.assertEqual(saved["equipment_items"][0]["facility"], "Radiology")

	# -- 4. resolve_role_user ------------------------------------------------------------------

	def test_resolve_role_user_returns_seeded_user_and_none_otherwise(self):
		frappe.set_user(self.manager_user)
		hub.save_project_profile(
			self.project,
			{
				"stakeholders": [
					{"role": self.role_pm, "party_name": "Jane PM", "user": self.manager_user},
					# A pure external party: a role with no `user` — must resolve to None, not
					# raise, per ARCHITECTURE_V2.md §2.
					{"role": self.role_client, "party_name": "Acme Client"},
				]
			},
		)

		self.assertEqual(project_profile.resolve_role_user(self.project, self.role_pm), self.manager_user)
		self.assertIsNone(project_profile.resolve_role_user(self.project, self.role_client))
		# Role never used as a stakeholder on this project at all.
		self.assertIsNone(project_profile.resolve_role_user(self.project, self.role_other))
		# No Profile row whatsoever for a fresh project -> None, not an exception.
		other_project = _make_project(self.company)
		self.assertIsNone(project_profile.resolve_role_user(other_project, self.role_pm))
		self.assertEqual(project_profile.get_stakeholders(other_project), [])

	# -- 5. get_project_context()["profile"] ----------------------------------------------------

	def test_get_project_context_profile_null_then_populated(self):
		frappe.set_user(self.manager_user)

		context = hub.get_project_context(self.project)
		self.assertIsNone(context["profile"])
		self.assertTrue(context["permissions"]["edit_profile"])

		hub.save_project_profile(
			self.project,
			{
				"project_code": "PC-CTX",
				"sector": "Healthcare",
				"stakeholders": [
					{"role": self.role_pm, "party_name": "Jane PM", "user": self.manager_user},
					{"role": self.role_other, "party_name": "Someone Else"},
				],
			},
		)

		context = hub.get_project_context(self.project)
		self.assertIsNotNone(context["profile"])
		self.assertEqual(context["profile"]["project_code"], "PC-CTX")
		self.assertEqual(context["profile"]["sector"], "Healthcare")

		key_roles = {row["role"] for row in context["profile"]["key_stakeholders"]}
		# Only the KEY_STAKEHOLDER_ROLES-listed role appears in the header summary...
		self.assertIn(self.role_pm, key_roles)
		# ...role_other is a real stakeholder on this project but not one of the five
		# header-relevant roles, so it must be filtered out here (still reachable via the
		# full list through get_project_profile()).
		self.assertNotIn(self.role_other, key_roles)

		pm_row = next(row for row in context["profile"]["key_stakeholders"] if row["role"] == self.role_pm)
		self.assertEqual(pm_row["user"], self.manager_user)
		self.assertTrue(pm_row["user_full_name"])

	# -- 6. edit_profile permission gate ---------------------------------------------------------

	def test_save_project_profile_denied_for_viewer_plus_projects_user(self):
		frappe.set_user(self.viewer_user)

		with self.assertRaises(frappe.PermissionError):
			hub.save_project_profile(self.project, {"project_code": "SHOULD-NOT-SAVE"})

		# The project-read gate alone must still let this user through to a plain read.
		hub.get_project_profile(self.project)
		self.assertFalse(hub.get_project_context(self.project)["permissions"]["edit_profile"])

	# -- 7. Stakeholder child rows round-trip -----------------------------------------------------

	def test_stakeholders_round_trip(self):
		frappe.set_user(self.manager_user)

		hub.save_project_profile(
			self.project,
			{
				"stakeholders": [
					{
						"role": self.role_pm,
						"party_name": "Jane PM",
						"user": self.manager_user,
						"is_primary": 1,
					},
					{
						"role": self.role_client,
						"party_name": "Acme Client",
						"organization": "Acme Inc",
					},
				]
			},
		)

		reloaded = hub.get_project_profile(self.project)
		self.assertEqual(len(reloaded["stakeholders"]), 2)

		by_role = {row["role"]: row for row in reloaded["stakeholders"]}
		self.assertEqual(by_role[self.role_pm]["party_name"], "Jane PM")
		self.assertEqual(by_role[self.role_pm]["user"], self.manager_user)
		self.assertTrue(by_role[self.role_pm]["is_primary"])
		self.assertEqual(by_role[self.role_client]["party_name"], "Acme Client")
		self.assertEqual(by_role[self.role_client]["organization"], "Acme Inc")
		self.assertFalse(by_role[self.role_client]["is_primary"])

		# The module-level contract (`project_profile.get_stakeholders`) must agree exactly —
		# other packages (the Submittal Workflow engine) read stakeholders through this
		# function, not through the Hub API.
		direct = project_profile.get_stakeholders(self.project)
		self.assertEqual(len(direct), 2)
		self.assertEqual({row.role for row in direct}, {self.role_pm, self.role_client})


def _get_or_create_stakeholder_role(role_name, is_egc_internal=0):
	if frappe.db.exists("EGC Stakeholder Role", role_name):
		return role_name
	frappe.get_doc(
		{
			"doctype": "EGC Stakeholder Role",
			"role_name": role_name,
			"is_egc_internal": is_egc_internal,
		}
	).insert(ignore_permissions=True)
	return role_name


def _make_wbs_node(project, code):
	doc = frappe.get_doc(
		{
			"doctype": "EGC WBS Node",
			"project": project,
			"wbs_code": code,
			"wbs_name": code,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_project(company):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-PP-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_user(email, roles):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
			}
		)
		user.insert(ignore_permissions=True)
	user.add_roles(*roles)
	return user.name
