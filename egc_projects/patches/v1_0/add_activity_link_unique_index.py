import frappe

from egc_projects.egc_projects.doctype.egc_activity_link.egc_activity_link import on_doctype_update


def execute():
	# `on_doctype_update` only fires when the DocType document itself is re-saved during a
	# sync, so a site that already has the table from an earlier version never gets the
	# constraint. Call it directly; `add_unique` is a no-op when the index already exists.
	if frappe.db.table_exists("EGC Activity Link"):
		on_doctype_update()
