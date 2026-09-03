# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Regression coverage for `install.py`'s `_remove_stale_project_field_order`.

A `field_order` Property Setter on `Project` (written whenever Desk's "Customize Form" is used
to drag-reorder fields) freezes the WHOLE doctype's field order as a static snapshot that
`Meta.sort_fields()` treats as authoritative over the doctype's own JSON `field_order` — silently
overriding it. A snapshot taken before this app's custom fields existed doesn't contain any of
their `insert_after` anchor points, which once pushed core's own `more_info_tab` (and everything
after it) to the very end of the native Project form. `create_project_custom_fields()` must
always clear a stale snapshot like this before running, so it can never silently recur.
"""

import frappe
from frappe.tests import IntegrationTestCase

from egc_projects import install


class TestInstallFieldOrderCleanup(IntegrationTestCase):
	def tearDown(self):
		name = frappe.db.get_value("Property Setter", {"doc_type": "Project", "property": "field_order"})
		if name:
			frappe.delete_doc("Property Setter", name, ignore_permissions=True, force=True)

	def _set_stale_field_order(self):
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doctype_or_field": "DocType",
				"doc_type": "Project",
				"property": "field_order",
				"property_type": "Text",
				"value": '["naming_series", "project_name"]',
			}
		).insert(ignore_permissions=True)

	def test_removes_a_stale_field_order_property_setter(self):
		self._set_stale_field_order()
		self.assertTrue(
			frappe.db.exists("Property Setter", {"doc_type": "Project", "property": "field_order"})
		)

		install._remove_stale_project_field_order()

		self.assertFalse(
			frappe.db.exists("Property Setter", {"doc_type": "Project", "property": "field_order"})
		)

	def test_is_a_no_op_when_no_field_order_property_setter_exists(self):
		install._remove_stale_project_field_order()  # must not raise
		self.assertFalse(
			frappe.db.exists("Property Setter", {"doc_type": "Project", "property": "field_order"})
		)

	def test_create_project_custom_fields_clears_it_before_running(self):
		self._set_stale_field_order()

		install.create_project_custom_fields()

		self.assertFalse(
			frappe.db.exists("Property Setter", {"doc_type": "Project", "property": "field_order"})
		)


class TestHideUnusedProjectFields(IntegrationTestCase):
	def _hidden_property_setter_value(self, fieldname):
		return frappe.db.get_value(
			"Property Setter", {"doc_type": "Project", "field_name": fieldname, "property": "hidden"}, "value"
		)

	def test_hides_every_field_in_the_list(self):
		install.hide_unused_project_fields()
		for fieldname in install._HIDDEN_PROJECT_FIELDS:
			self.assertEqual(
				self._hidden_property_setter_value(fieldname), "1", f"{fieldname} was not hidden"
			)

	def test_is_idempotent(self):
		install.hide_unused_project_fields()
		install.hide_unused_project_fields()  # must not raise or duplicate
		self.assertEqual(
			frappe.db.count(
				"Property Setter", {"doc_type": "Project", "field_name": "priority", "property": "hidden"}
			),
			1,
		)

	def test_hides_native_users_table_and_egc_hr_supervisors_table(self):
		install.hide_unused_project_fields()
		self.assertEqual(self._hidden_property_setter_value("users"), "1")
		self.assertEqual(self._hidden_property_setter_value("custom_egc_supervisors"), "1")

	def test_sales_order_department_cost_center_stay_visible(self):
		# Corrected 2026-08-30 — these were wrongly hidden on "nothing in this app's own code
		# reads them," which isn't the same as "nobody uses them" (sales_order in particular is
		# a plain native field a PM links directly from the Project form).
		install.hide_unused_project_fields()
		for fieldname in install._PREVIOUSLY_HIDDEN_IN_ERROR:
			self.assertIsNone(self._hidden_property_setter_value(fieldname), f"{fieldname} should not be hidden")

	def test_unhides_a_field_a_stale_earlier_run_had_hidden(self):
		# Simulates a site that ran an OLDER version of this function, before the fix — the
		# Property Setter it wrote must be cleaned up by a fresh run, not just skipped from here
		# on for new installs.
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		make_property_setter("Project", "sales_order", "hidden", 1, "Check")
		self.assertEqual(self._hidden_property_setter_value("sales_order"), "1")

		install.hide_unused_project_fields()

		self.assertIsNone(self._hidden_property_setter_value("sales_order"))


class TestTrimPercentCompleteMethodOptions(IntegrationTestCase):
	def test_trims_to_manual_and_activity_completion_only(self):
		install.create_activity_completion_method_option()  # the 5-option widened list first
		install.trim_percent_complete_method_options()

		value = frappe.db.get_value(
			"Property Setter",
			{"doc_type": "Project", "field_name": "percent_complete_method", "property": "options"},
			"value",
		)
		self.assertEqual(value, "Manual\nActivity Completion")

	def test_field_stays_visible(self):
		install.trim_percent_complete_method_options()
		self.assertIsNone(
			frappe.db.get_value(
				"Property Setter",
				{"doc_type": "Project", "field_name": "percent_complete_method", "property": "hidden"},
			)
		)

	def test_resets_stale_task_completion_values_to_activity_completion(self):
		from egc_projects.egc_projects.project_progress import PERCENT_COMPLETE_METHOD

		company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
		project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"Trim-Test-{frappe.generate_hash(length=6)}", "company": company}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Project", project.name, "percent_complete_method", "Task Completion")

		install.trim_percent_complete_method_options()

		# "Task Completion" -> PERCENT_COMPLETE_METHOD, not "Manual" — _should_sync() already
		# treated "Task Completion" as its own auto-sync sentinel, so this preserves that
		# project's existing sync behavior instead of silently disabling it.
		self.assertEqual(
			frappe.db.get_value("Project", project.name, "percent_complete_method"), PERCENT_COMPLETE_METHOD
		)
		# Must actually be savable now, not just correct in the database.
		frappe.get_doc("Project", project.name).save(ignore_permissions=True)

	def test_resets_stale_task_progress_and_weight_values_to_manual(self):
		company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
		project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"Trim-Test-{frappe.generate_hash(length=6)}", "company": company}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Project", project.name, "percent_complete_method", "Task Weight")

		install.trim_percent_complete_method_options()

		# _should_sync() never had a case for "Task Progress"/"Task Weight" (no sync happened),
		# same as "Manual" — this is also a preserving rename, not a behavior change.
		self.assertEqual(frappe.db.get_value("Project", project.name, "percent_complete_method"), "Manual")
		frappe.get_doc("Project", project.name).save(ignore_permissions=True)


class TestRaiseProjectAttachmentLimit(IntegrationTestCase):
	def test_raises_the_effective_meta_limit(self):
		install.raise_project_attachment_limit()
		frappe.clear_cache(doctype="Project")
		self.assertEqual(frappe.get_meta("Project").max_attachments, install.PROJECT_MAX_ATTACHMENTS)

	def test_is_idempotent(self):
		install.raise_project_attachment_limit()
		install.raise_project_attachment_limit()
		rows = frappe.get_all(
			"Property Setter", filters={"doc_type": "Project", "property": "max_attachments"}, fields=["name"]
		)
		self.assertEqual(len(rows), 1)


class TestRemoveAdminProjectOverscoping(IntegrationTestCase):
	"""Regression coverage for a real bug: `grant_portal_access` used to scope an admin (System
	Manager/Projects Manager) with a `Project` User Permission just like anyone else — but Frappe's
	own User Permission enforcement has no role-based bypass, so even one such row cost that admin
	visibility of every OTHER project, regardless of role. This is what repairs an
	already-affected account on the next `bench migrate`, not just prevents new ones."""

	def _make_project(self):
		company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
		return frappe.get_doc(
			{"doctype": "Project", "project_name": f"EGC-Overscope-Test-{frappe.generate_hash(length=8)}", "company": company}
		).insert(ignore_permissions=True).name

	def _make_user(self, email, roles):
		if frappe.db.exists("User", email):
			user = frappe.get_doc("User", email)
		else:
			user = frappe.get_doc(
				{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		user.add_roles(*roles)
		return user.name

	def tearDown(self):
		names = frappe.get_all(
			"User Permission", filters={"allow": "Project", "user": ("like", "overscope-test-%")}, pluck="name"
		)
		for name in names:
			frappe.delete_doc("User Permission", name, ignore_permissions=True, force=True)

	def test_removes_a_stale_grant_for_a_bypass_role_holder(self):
		project = self._make_project()
		admin = self._make_user("overscope-test-admin@example.com", ["System Manager"])
		frappe.get_doc(
			{"doctype": "User Permission", "user": admin, "allow": "Project", "for_value": project}
		).insert(ignore_permissions=True)

		install.remove_admin_project_overscoping()

		self.assertFalse(frappe.db.exists("User Permission", {"user": admin, "allow": "Project"}))

	def test_leaves_a_legitimately_scoped_non_admin_user_alone(self):
		project = self._make_project()
		viewer = self._make_user("overscope-test-viewer@example.com", ["Projects User"])
		frappe.get_doc(
			{"doctype": "User Permission", "user": viewer, "allow": "Project", "for_value": project}
		).insert(ignore_permissions=True)

		install.remove_admin_project_overscoping()

		self.assertTrue(
			frappe.db.exists("User Permission", {"user": viewer, "allow": "Project", "for_value": project})
		)


class TestRemoveInternalStakeholderOverscoping(IntegrationTestCase):
	"""Regression coverage for the second instance of the same bug `TestRemoveAdminProjectOverscoping`
	covers: `grant_portal_access` used to scope an internal EGC stakeholder (Document Controller,
	Project Engineer, ...) with a `Project` User Permission too, not just external parties — but
	their Stakeholder Role already grants a real EGC role meant to work across every project, so
	that one scoping row silently cost them visibility of every OTHER Project-linked doctype
	(Purchase Order, Purchase Invoice, Timesheet, ...) system-wide. Hit live in production: an
	internal Document Controller granted access to one project lost Purchase Order/Invoice
	visibility everywhere else. This is what repairs an already-affected account on the next
	`bench migrate`, checked per (user, project) pair against that project's own Directory row."""

	def _make_project(self):
		company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
		return frappe.get_doc(
			{"doctype": "Project", "project_name": f"EGC-IntOverscope-Test-{frappe.generate_hash(length=8)}", "company": company}
		).insert(ignore_permissions=True).name

	def _make_user(self, email):
		if frappe.db.exists("User", email):
			return email
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		return email

	def _make_role(self, role_name, is_egc_internal):
		if frappe.db.exists("EGC Stakeholder Role", role_name):
			return role_name
		frappe.get_doc(
			{"doctype": "EGC Stakeholder Role", "role_name": role_name, "is_egc_internal": is_egc_internal}
		).insert(ignore_permissions=True)
		return role_name

	def _add_stakeholder(self, project, role, person):
		doc = frappe.get_doc("Project", project)
		doc.append("custom_egc_stakeholders", {"role": role, "party_name": person, "person": person})
		doc.save(ignore_permissions=True)

	def tearDown(self):
		names = frappe.get_all(
			"User Permission", filters={"allow": "Project", "user": ("like", "int-overscope-test-%")}, pluck="name"
		)
		for name in names:
			frappe.delete_doc("User Permission", name, ignore_permissions=True, force=True)

	def test_removes_a_stale_grant_for_an_internal_stakeholder(self):
		project = self._make_project()
		role = self._make_role("EGC-Install-Test-Internal Role", is_egc_internal=1)
		user = self._make_user("int-overscope-test-doccon@example.com")
		self._add_stakeholder(project, role, user)
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Project", "for_value": project}
		).insert(ignore_permissions=True)

		install.remove_internal_stakeholder_overscoping()

		self.assertFalse(frappe.db.exists("User Permission", {"user": user, "allow": "Project", "for_value": project}))

	def test_leaves_a_genuinely_external_stakeholder_alone(self):
		project = self._make_project()
		role = self._make_role("EGC-Install-Test-External Role", is_egc_internal=0)
		user = self._make_user("int-overscope-test-client@example.com")
		self._add_stakeholder(project, role, user)
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Project", "for_value": project}
		).insert(ignore_permissions=True)

		install.remove_internal_stakeholder_overscoping()

		self.assertTrue(frappe.db.exists("User Permission", {"user": user, "allow": "Project", "for_value": project}))

	def test_leaves_a_different_projects_external_scoping_alone_for_the_same_person(self):
		# The precision the per-(user, project) check exists for: this person is an internal
		# stakeholder on `internal_project` but genuinely external (a different hat) on
		# `other_project` — only the internal-project scoping row should be removed.
		internal_project = self._make_project()
		other_project = self._make_project()
		internal_role = self._make_role("EGC-Install-Test-Internal Role", is_egc_internal=1)
		external_role = self._make_role("EGC-Install-Test-External Role", is_egc_internal=0)
		user = self._make_user("int-overscope-test-dualhat@example.com")
		self._add_stakeholder(internal_project, internal_role, user)
		self._add_stakeholder(other_project, external_role, user)
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Project", "for_value": internal_project}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "User Permission", "user": user, "allow": "Project", "for_value": other_project}
		).insert(ignore_permissions=True)

		install.remove_internal_stakeholder_overscoping()

		self.assertFalse(
			frappe.db.exists("User Permission", {"user": user, "allow": "Project", "for_value": internal_project})
		)
		self.assertTrue(
			frappe.db.exists("User Permission", {"user": user, "allow": "Project", "for_value": other_project})
		)
