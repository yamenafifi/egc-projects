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
