# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for Project Information (ARCHITECTURE_V2.md §1/§2/§3): `custom_egc_*` fields on the
core `Project` doctype (see `project_custom_fields.py`), `project_profile.py`'s stable
`resolve_role_user`/`get_stakeholders` contract, and `api/hub.py`'s `get_project_info` /
extended `get_project_context`.

There is no `save_project_info` — this data is edited on the native `Project` form now, not
through the Hub, so every fixture here writes directly to `Project` via `frappe.get_doc(...)
.save()`, exactly as a user editing the native form would.

Fixture style matches `test_hub_api.py`: one shared set of masters in `setUpClass`, one
dedicated `Project` per test in `setUp`. EGC roles are additive and grant nothing on core
`Project` (docs/ARCHITECTURE.md §4), so `viewer_user` is built with `Projects User` as well as
`EGC Project Viewer`.
"""

import frappe
from frappe.tests import IntegrationTestCase

from egc_projects.api import hub
from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import project_profile


class TestProjectInfo(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]

		# "EGC Project Manager" and "Client" are two of the five names ARCHITECTURE_V2.md §4
		# hard-wires as `project_profile.KEY_STAKEHOLDER_ROLES` — used to exercise the
		# `get_project_context()["profile"]["key_stakeholders"]` filtering.
		cls.role_pm = _get_or_create_stakeholder_role("EGC Project Manager", is_egc_internal=1)
		cls.role_client = _get_or_create_stakeholder_role("Client", is_egc_internal=0)
		# Deliberately NOT in KEY_STAKEHOLDER_ROLES, so it can prove both "role not present"
		# (resolve_role_user) and "present but filtered out of the header summary" (hub context).
		cls.role_other = _get_or_create_stakeholder_role("EGC-PI-Test Other Role", is_egc_internal=1)

		cls.manager_user = _get_or_create_user(
			"egc-pi-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		cls.viewer_user = _get_or_create_user(
			"egc-pi-viewer@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER]
		)

	def setUp(self):
		self.project = _make_project(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")

	# -- fixtures ------------------------------------------------------------------------------

	def _set_project_fields(self, **values):
		"""Mirrors editing the native `Project` form's "EGC Project Info" tab directly."""
		doc = frappe.get_doc("Project", self.project)
		for fieldname, value in values.items():
			doc.set(fieldname, value)
		doc.save(ignore_permissions=True)
		return doc

	def _add_stakeholder(self, role, user=None, party_name=None):
		doc = frappe.get_doc("Project", self.project)
		doc.append("custom_egc_stakeholders", {"role": role, "party_name": party_name, "user": user})
		doc.save(ignore_permissions=True)
		return doc

	# -- 1. get_project_info reads straight off Project's own fields -------------------------

	def test_get_project_info_defaults_empty_on_a_fresh_project(self):
		frappe.set_user(self.manager_user)

		result = hub.get_project_info(self.project)
		self.assertEqual(result["project"], self.project)
		self.assertIsNone(result["project_code"])
		# Select fields default to "", not None — same "unset" representation the old Profile
		# doctype used, since nothing about a Select field's storage changed.
		self.assertEqual(result["sector"], "")
		self.assertEqual(result["stakeholders"], [])
		self.assertEqual(result["equipment_items"], [])

	def test_get_project_info_reflects_fields_set_on_the_native_form(self):
		self._set_project_fields(
			custom_egc_project_code="PC-001",
			custom_egc_sector="Healthcare",
			custom_egc_contract_value=125000,
		)

		frappe.set_user(self.manager_user)
		result = hub.get_project_info(self.project)
		self.assertEqual(result["project_code"], "PC-001")
		self.assertEqual(result["sector"], "Healthcare")
		self.assertEqual(result["contract_value"], 125000)

	# -- 1b. An untouched Select field must stay unset, never silently default to its first
	#         option (regression — carried over from the old EGC Project Profile doctype) ------

	def test_untouched_select_fields_stay_empty(self):
		"""Frappe's `get_new_doc()` defaults a Select field with no explicit value to the FIRST
		line of its `options` string, unless that string begins with a blank line. Every
		optional Select in `project_custom_fields.py` (stage/sector/delivery_method/
		contract_type) must carry that leading blank line — this is a fresh custom Project row,
		not a new-record default path, so this proves the fields themselves are declared right,
		not just that one save path happens to avoid the bug.
		"""
		row = frappe.db.get_value(
			"Project",
			self.project,
			["custom_egc_project_stage", "custom_egc_sector", "custom_egc_delivery_method", "custom_egc_contract_type"],
			as_dict=True,
		)
		self.assertEqual(row.custom_egc_project_stage, "")
		self.assertEqual(row.custom_egc_sector, "")
		self.assertEqual(row.custom_egc_delivery_method, "")
		self.assertEqual(row.custom_egc_contract_type, "")

	# -- 2. Cross-project WBS node on an equipment item is rejected (Project's own validate) ---

	def test_equipment_item_wbs_node_cross_project_rejected(self):
		other_project = _make_project(self.company)
		other_wbs = _make_wbs_node(other_project, "EQ-X")

		doc = frappe.get_doc("Project", self.project)
		doc.append("custom_egc_equipment_items", {"facility": "Radiology", "wbs_node": other_wbs})
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)

	def test_equipment_item_wbs_node_same_project_accepted(self):
		wbs = _make_wbs_node(self.project, "EQ-OK")

		doc = self._set_project_fields()
		doc.append("custom_egc_equipment_items", {"facility": "Radiology", "wbs_node": wbs})
		doc.save(ignore_permissions=True)

		frappe.set_user(self.manager_user)
		result = hub.get_project_info(self.project)
		self.assertEqual(len(result["equipment_items"]), 1)
		self.assertEqual(result["equipment_items"][0]["wbs_node"], wbs)
		self.assertEqual(result["equipment_items"][0]["facility"], "Radiology")

	# -- 3. resolve_role_user ------------------------------------------------------------------

	def test_resolve_role_user_returns_seeded_user_and_none_otherwise(self):
		self._add_stakeholder(self.role_pm, user=self.manager_user, party_name="Jane PM")
		# A pure external party: a role with no `user` — must resolve to None, not raise, per
		# ARCHITECTURE_V2.md §2.
		self._add_stakeholder(self.role_client, party_name="Acme Client")

		self.assertEqual(project_profile.resolve_role_user(self.project, self.role_pm), self.manager_user)
		self.assertIsNone(project_profile.resolve_role_user(self.project, self.role_client))
		# Role never used as a stakeholder on this project at all.
		self.assertIsNone(project_profile.resolve_role_user(self.project, self.role_other))
		# A project with zero stakeholders -> None/[], not an exception.
		other_project = _make_project(self.company)
		self.assertIsNone(project_profile.resolve_role_user(other_project, self.role_pm))
		self.assertEqual(project_profile.get_stakeholders(other_project), [])

	# -- 4. get_project_context()["profile"] — always a dict now, never None -------------------

	def test_get_project_context_profile_always_present(self):
		frappe.set_user(self.manager_user)

		context = hub.get_project_context(self.project)
		self.assertIsNotNone(context["profile"])
		self.assertIsNone(context["profile"]["project_code"])
		self.assertTrue(context["permissions"]["edit_profile"])

		self._set_project_fields(custom_egc_project_code="PC-CTX", custom_egc_sector="Healthcare")
		self._add_stakeholder(self.role_pm, user=self.manager_user, party_name="Jane PM")
		self._add_stakeholder(self.role_other, party_name="Someone Else")

		context = hub.get_project_context(self.project)
		self.assertEqual(context["profile"]["project_code"], "PC-CTX")
		self.assertEqual(context["profile"]["sector"], "Healthcare")

		key_roles = {row["role"] for row in context["profile"]["key_stakeholders"]}
		# Only the KEY_STAKEHOLDER_ROLES-listed role appears in the header summary...
		self.assertIn(self.role_pm, key_roles)
		# ...role_other is a real stakeholder on this project but not one of the five
		# header-relevant roles, so it must be filtered out here (still reachable via the full
		# list through get_project_info()).
		self.assertNotIn(self.role_other, key_roles)

		pm_row = next(row for row in context["profile"]["key_stakeholders"] if row["role"] == self.role_pm)
		self.assertEqual(pm_row["user"], self.manager_user)
		self.assertTrue(pm_row["user_full_name"])

	# -- 5. edit_profile is exactly "can this user write to Project" ---------------------------

	def test_edit_profile_matches_project_write_permission(self):
		# `Projects User` (the baseline role every Hub user must hold, per docs/ARCHITECTURE.md
		# §4) already grants `write` on core `Project` out of the box — so this deliberately
		# does not assert a denied case: with this app's role model, anyone who can open the Hub
		# at all can already edit the native Project form, EGC Info tab included. That is
		# reality, not a gap this endpoint should paper over. What must hold is that the flag
		# never diverges from `frappe.has_permission` — asserted independently, not by trusting
		# the same code path this endpoint itself calls.
		frappe.set_user(self.manager_user)
		context = hub.get_project_context(self.project)
		self.assertEqual(
			context["permissions"]["edit_profile"],
			bool(frappe.has_permission("Project", "write", doc=self.project)),
		)
		self.assertTrue(context["permissions"]["edit_profile"])

	# -- 6. Stakeholder child rows round-trip -----------------------------------------------------

	def test_stakeholders_round_trip(self):
		self._add_stakeholder(self.role_pm, user=self.manager_user, party_name="Jane PM")
		doc = frappe.get_doc("Project", self.project)
		doc.custom_egc_stakeholders[-1].is_primary = 1
		doc.append(
			"custom_egc_stakeholders",
			{"role": self.role_client, "party_name": "Acme Client", "organization": "Acme Inc"},
		)
		doc.save(ignore_permissions=True)

		frappe.set_user(self.manager_user)
		reloaded = hub.get_project_info(self.project)
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
			"project_name": f"EGC-PI-Test-{frappe.generate_hash(length=8)}",
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
