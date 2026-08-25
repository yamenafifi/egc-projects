// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.ui.form.on("EGC Project Document Revision", {
	refresh(frm) {
		frm.set_query("document", () => {
			if (frm.doc.project) {
				return { filters: { project: frm.doc.project } };
			}
			return {};
		});

		if (frm.doc.docstatus === 0) {
			frm.set_intro(
				__(
					"Submitting this revision issues it permanently: the file can never be replaced afterwards, and any previously current revision of this document becomes Superseded. Only Draft revisions can be deleted."
				),
				"orange"
			);
		} else {
			frm.set_intro("");
		}
	},
});
