# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import random_string

from egc_projects.egc_projects.doctype.egc_wbs_node.egc_wbs_node import get_children


def get_or_create_test_company() -> str:
	existing = frappe.db.get_value("Company", {}, "name")
	if existing:
		return existing

	abbr = "TWC"
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": "_Test WBS Company",
			"abbr": abbr,
			"default_currency": "USD",
			"country": "United Arab Emirates",
		}
	)
	company.insert(ignore_permissions=True)
	return company.name


def make_test_project(company: str, suffix: str) -> "frappe.Document":
	project = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"_Test WBS Project {suffix}",
			"naming_series": "PROJ-.####",
			"company": company,
		}
	)
	project.insert(ignore_permissions=True)
	return project


def make_wbs_node(project: str, wbs_code: str, wbs_name: str | None = None, **kwargs) -> "frappe.Document":
	doc = frappe.get_doc(
		{
			"doctype": "EGC WBS Node",
			"project": project,
			"wbs_code": wbs_code,
			"wbs_name": wbs_name or wbs_code,
			**kwargs,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestEGCWBSNode(IntegrationTestCase):
	@classmethod
	def setUpClass(cls) -> None:
		super().setUpClass()
		frappe.set_user("Administrator")

		company = get_or_create_test_company()
		suffix = random_string(8)
		cls.project_a = make_test_project(company, f"A-{suffix}")
		cls.project_b = make_test_project(company, f"B-{suffix}")

	def test_four_level_tree_nests_correctly(self) -> None:
		level1 = make_wbs_node(self.project_a.name, "T4-L1", is_group=1)
		level2 = make_wbs_node(
			self.project_a.name, "T4-L2", is_group=1, parent_egc_wbs_node=level1.name
		)
		level3 = make_wbs_node(
			self.project_a.name, "T4-L3", is_group=1, parent_egc_wbs_node=level2.name
		)
		level4 = make_wbs_node(
			self.project_a.name, "T4-L4", is_group=0, parent_egc_wbs_node=level3.name
		)

		lft_rgt = {
			node.name: frappe.db.get_value("EGC WBS Node", node.name, ["lft", "rgt"], as_dict=True)
			for node in (level1, level2, level3, level4)
		}

		# each level must strictly nest inside its parent: lft grows inward, rgt shrinks inward
		self.assertLess(lft_rgt[level1.name].lft, lft_rgt[level2.name].lft)
		self.assertLess(lft_rgt[level2.name].lft, lft_rgt[level3.name].lft)
		self.assertLess(lft_rgt[level3.name].lft, lft_rgt[level4.name].lft)

		self.assertLess(lft_rgt[level4.name].lft, lft_rgt[level4.name].rgt)
		self.assertLess(lft_rgt[level4.name].rgt, lft_rgt[level3.name].rgt)
		self.assertLess(lft_rgt[level3.name].rgt, lft_rgt[level2.name].rgt)
		self.assertLess(lft_rgt[level2.name].rgt, lft_rgt[level1.name].rgt)

	def test_parent_from_another_project_is_rejected(self) -> None:
		other_root = make_wbs_node(self.project_b.name, "XP-ROOT", is_group=1)

		child = frappe.get_doc(
			{
				"doctype": "EGC WBS Node",
				"project": self.project_a.name,
				"wbs_code": "XP-CHILD",
				"wbs_name": "XP-CHILD",
				"parent_egc_wbs_node": other_root.name,
			}
		)
		self.assertRaises(frappe.ValidationError, child.insert, ignore_permissions=True)

	def test_parent_must_be_a_group(self) -> None:
		leaf = make_wbs_node(self.project_a.name, "NG-LEAF", is_group=0)

		child = frappe.get_doc(
			{
				"doctype": "EGC WBS Node",
				"project": self.project_a.name,
				"wbs_code": "NG-CHILD",
				"wbs_name": "NG-CHILD",
				"parent_egc_wbs_node": leaf.name,
			}
		)
		self.assertRaises(frappe.ValidationError, child.insert, ignore_permissions=True)

	def test_wbs_code_unique_per_project_only(self) -> None:
		make_wbs_node(self.project_a.name, "DUP-CODE")

		duplicate_same_project = frappe.get_doc(
			{
				"doctype": "EGC WBS Node",
				"project": self.project_a.name,
				"wbs_code": "DUP-CODE",
				"wbs_name": "Duplicate in same project",
			}
		)
		self.assertRaises(
			frappe.DuplicateEntryError, duplicate_same_project.insert, ignore_permissions=True
		)

		# the same code in a *different* project is a legitimate, separate record
		other_project_node = make_wbs_node(self.project_b.name, "DUP-CODE")
		self.assertEqual(other_project_node.project, self.project_b.name)

	def test_get_children_is_scoped_to_project(self) -> None:
		a_root = make_wbs_node(self.project_a.name, "GC-A-ROOT", is_group=1)
		make_wbs_node(self.project_a.name, "GC-A-CHILD", parent_egc_wbs_node=a_root.name)
		make_wbs_node(self.project_b.name, "GC-B-ROOT", is_group=1)

		frappe.set_user("Administrator")
		roots = get_children(
			doctype="EGC WBS Node", parent=self.project_a.name, project=self.project_a.name, is_root=True
		)
		root_values = {row["value"] for row in roots}

		self.assertIn(a_root.name, root_values)
		for name in root_values:
			self.assertEqual(frappe.db.get_value("EGC WBS Node", name, "project"), self.project_a.name)

		children = get_children(
			doctype="EGC WBS Node", parent=a_root.name, project=self.project_a.name, is_root=False
		)
		child_values = {row["value"] for row in children}
		self.assertEqual(child_values, {f"{self.project_a.name}-GC-A-CHILD"})

		self.assertRaises(frappe.ValidationError, get_children, doctype="EGC WBS Node", project=None)
