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
