// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.ui.form.on("EGC Change Order", {
	refresh(frm) {
		frm.set_query("sales_order", () => ({
			filters: { project: frm.doc.project, docstatus: 1 },
		}));

		if (frm.doc.docstatus === 0) {
			frm.set_intro(
				__(
					"Submitting this Change Order IS the approval step — the linked Sales Order's amount becomes part of the project's approved contract value the moment this is submitted."
				),
				"orange"
			);
		} else {
			frm.set_intro("");
		}
	},
	project(frm) {
		frm.set_value("sales_order", null);
	},
});
