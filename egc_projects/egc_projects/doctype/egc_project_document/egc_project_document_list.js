// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.listview_settings["EGC Project Document"] = {
	add_fields: ["approval_status", "document_status", "current_revision_label"],
	get_indicator(doc) {
		const color_by_approval_status = {
			"Not Submitted": "gray",
			"Under Review": "orange",
			Approved: "green",
			"Approved with Comments": "yellow",
			"Revise & Resubmit": "red",
			Rejected: "red",
		};
		const color = color_by_approval_status[doc.approval_status] || "gray";
		return [__(doc.approval_status), color, `approval_status,=,${doc.approval_status}`];
	},
};
