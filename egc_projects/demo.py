"""Reproducible demo dataset — the acceptance scenarios from the build brief, as real records.

Useful for exploring the Project Hub on a fresh site and for eyeballing behaviour that the
automated suite asserts headlessly. Everything it creates is scoped to one clearly-named
project, and `purge()` removes all of it.

	bench --site <site> execute egc_projects.demo.seed
	bench --site <site> execute egc_projects.demo.purge
"""

import frappe
from frappe.utils import add_days, today

PROJECT_NAME = "KFSH MRI Expansion (EGC DEMO)"


def _project() -> str:
	existing = frappe.db.get_value("Project", {"project_name": PROJECT_NAME}, "name")
	if existing:
		return existing

	company = frappe.db.get_value("Company", {}, "name")
	if not company:
		frappe.throw("A Company is required before seeding the EGC Projects demo data.")

	return frappe.get_doc(
		{"doctype": "Project", "project_name": PROJECT_NAME, "company": company}
	).insert().name


def seed() -> str:
	project = _project()

	def wbs(code, name, parent=None, is_group=0, discipline=None, sequence=0):
		return frappe.get_doc(
			{
				"doctype": "EGC WBS Node",
				"project": project,
				"wbs_code": code,
				"wbs_name": name,
				"parent_egc_wbs_node": parent,
				"is_group": is_group,
				"discipline": discipline,
				"sequence": sequence,
			}
		).insert().name

	root = wbs("01", "KFSH MRI", is_group=1, sequence=1)
	wbs("01.01", "Architectural", root, 0, "ARCH", 1)
	mechanical = wbs("01.02", "Mechanical", root, 1, "MECH", 2)
	hvac = wbs("01.02.01", "HVAC", mechanical, 1, "MECH", 1)
	mri_hvac = wbs("01.02.01.01", "MRI Area HVAC", hvac, 0, "MECH", 1)
	wbs("01.03", "Electrical", root, 0, "ELEC", 3)
	wbs("01.04", "Civil", root, 0, "CIVIL", 4)

	def activity(code, name, parent=None, is_group=0, node=None, status="Not Started", pct=0, end=None, sequence=0):
		return frappe.get_doc(
			{
				"doctype": "EGC Activity",
				"project": project,
				"activity_code": code,
				"activity_name": name,
				"parent_egc_activity": parent,
				"is_group": is_group,
				"wbs_node": node,
				"discipline": "MECH",
				"status": status,
				"percent_complete": pct,
				"planned_end_date": end,
				"sequence": sequence,
			}
		).insert().name

	ductwork = activity("MECH-HVAC-001", "HVAC Ductwork", None, 1, hvac, "In Progress", 40, add_days(today(), 20), 1)
	fabrication = activity("MECH-HVAC-002", "Fabrication", ductwork, 0, hvac, "Completed", 100, add_days(today(), -10), 1)
	installation = activity("MECH-HVAC-003", "Installation", ductwork, 1, mri_hvac, "In Progress", 30, add_days(today(), -2), 2)
	mri_01 = activity("MECH-HVAC-004", "MRI-01", installation, 0, mri_hvac, "In Progress", 50, add_days(today(), -5), 1)
	mri_02 = activity("MECH-HVAC-005", "MRI-02", installation, 0, mri_hvac, "Not Started", 0, add_days(today(), 15), 2)
	activity("MECH-HVAC-006", "Testing", ductwork, 0, hvac, "Not Started", 0, add_days(today(), 30), 3)

	attachment = frappe.get_doc(
		{"doctype": "File", "file_name": "m-101-rev00.txt", "is_private": 1, "content": "EGC demo drawing"}
	).insert().file_url

	drawing = frappe.get_doc(
		{
			"doctype": "EGC Project Document",
			"project": project,
			"document_number": "M-101",
			"title": "HVAC Coordination Drawing",
			"document_type": "Drawing",
			"discipline": "MECH",
			"wbs_node": hvac,
		}
	).insert()

	revision = frappe.get_doc(
		{
			"doctype": "EGC Project Document Revision",
			"document": drawing.name,
			"revision": "00",
			"file": attachment,
			"revision_date": today(),
		}
	).insert()
	revision.submit()

	from egc_projects.egc_projects import relationships

	# One drawing, three activities — the many-to-many case, with no duplicated drawing.
	for name in (fabrication, mri_01, mri_02):
		relationships.add_link(name, "EGC Project Document", drawing.name)

	submittal = frappe.get_doc(
		{
			"doctype": "EGC Submittal",
			"project": project,
			"submittal_number": "SUB-MECH-0027",
			"title": "HVAC Shop Drawings - MRI Department",
			"submittal_type": "Shop Drawing",
			"discipline": "MECH",
			"wbs_node": hvac,
		}
	).insert()

	submission = frappe.get_doc(
		{
			"doctype": "EGC Submittal Revision",
			"submittal": submittal.name,
			"revision_label": "00",
			"date_submitted": today(),
			"due_date": add_days(today(), -1),
			"documents": [{"document_revision": revision.name}],
		}
	).insert()
	submission.submit()

	for name in (mri_01, mri_02):
		relationships.add_link(name, "EGC Submittal", submittal.name)

	frappe.db.commit()
	return project


def purge(project_name: str | None = None) -> None:
	"""Remove everything `seed()` created, through the app's own lifecycle."""
	project = frappe.db.get_value("Project", {"project_name": project_name or PROJECT_NAME}, "name")
	if not project:
		return

	for link in frappe.get_all("EGC Activity Link", filters={"project": project}, pluck="name"):
		frappe.delete_doc("EGC Activity Link", link)

	for submittal in frappe.get_all("EGC Submittal", filters={"project": project}, pluck="name"):
		for row in frappe.get_all("EGC Submittal Revision", filters={"submittal": submittal}, fields=["name", "docstatus"]):
			doc = frappe.get_doc("EGC Submittal Revision", row.name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("EGC Submittal Revision", doc.name)
		frappe.delete_doc("EGC Submittal", submittal)

	for document in frappe.get_all("EGC Project Document", filters={"project": project}, pluck="name"):
		for row in frappe.get_all("EGC Project Document Revision", filters={"document": document}, fields=["name", "docstatus"]):
			doc = frappe.get_doc("EGC Project Document Revision", row.name)
			if doc.docstatus == 1:
				doc.cancel()
			frappe.delete_doc("EGC Project Document Revision", doc.name)
		frappe.delete_doc("EGC Project Document", document)

	for doctype in ("EGC Activity", "EGC WBS Node"):
		for name in frappe.get_all(doctype, filters={"project": project}, pluck="name", order_by="lft desc"):
			frappe.delete_doc(doctype, name)

	# EGC Project Profile links to Project by name (its own `name` field IS the project's), so
	# it must go before the Project itself or `delete_doc("Project", ...)` raises a
	# LinkExistsError — new v2 doctypes that reference Project the same way belong in this list.
	if frappe.db.exists("EGC Project Profile", project):
		frappe.delete_doc("EGC Project Profile", project)

	frappe.delete_doc("Project", project)
	frappe.db.commit()
