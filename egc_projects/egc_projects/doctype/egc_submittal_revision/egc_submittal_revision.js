// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.ui.form.on("EGC Submittal Revision", {
	refresh(frm) {
		frm.set_query("submittal", () => ({}));
		frm.set_query("document_revision", "documents", () => ({
			filters: { project: frm.doc.project, docstatus: 1 },
		}));

		if (frm.doc.docstatus === 0) {
			frm.set_intro(
				__(
					"Submitting this submission sends it for review: it must carry at least one Issued document revision. Response fields are written only by the review workflow, never edited directly."
				),
				"orange"
			);
		} else {
			frm.set_intro("");
		}

		if (frm.doc.docstatus === 1) {
			if (frm.doc.submission_status === "Submitted") {
				frm.add_custom_button(__("Mark Under Review"), () => mark_under_review(frm));
			}
			if (["Submitted", "Under Review"].includes(frm.doc.submission_status)) {
				frm.add_custom_button(__("Record Response"), () => record_response(frm)).addClass(
					"btn-primary"
				);
			}
		}
	},
});

function mark_under_review(frm) {
	frappe.call({
		method: "egc_projects.egc_projects.submittal_control.mark_under_review",
		args: { submission: frm.doc.name },
		freeze: true,
		callback() {
			frm.reload_doc();
		},
	});
}

function record_response(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Record Response"),
		fields: [
			{
				fieldname: "response",
				fieldtype: "Select",
				label: __("Response"),
				options: ["Approved", "Approved with Comments", "Revise & Resubmit", "Rejected"],
				reqd: 1,
			},
			{
				fieldname: "response_date",
				fieldtype: "Date",
				label: __("Response Date"),
				default: frappe.datetime.get_today(),
			},
			{
				fieldname: "remarks",
				fieldtype: "Text",
				label: __("Remarks"),
			},
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			frappe.call({
				method: "egc_projects.egc_projects.submittal_control.record_response",
				args: {
					submission: frm.doc.name,
					response: values.response,
					remarks: values.remarks,
					response_date: values.response_date,
				},
				freeze: true,
				callback() {
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
}
