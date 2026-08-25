// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.listview_settings["EGC Submittal"] = {
	add_fields: ["submittal_status", "current_submission_label", "current_due_date"],
	get_indicator(doc) {
		const color_by_submittal_status = {
			Draft: "gray",
			Submitted: "orange",
			"Under Review": "orange",
			Approved: "green",
			"Approved with Comments": "blue",
			"Revise & Resubmit": "red",
			Rejected: "red",
		};
		const color = color_by_submittal_status[doc.submittal_status] || "gray";
		return [__(doc.submittal_status), color, `submittal_status,=,${doc.submittal_status}`];
	},
};
