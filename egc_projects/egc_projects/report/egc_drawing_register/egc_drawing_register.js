// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.query_reports["EGC Drawing Register"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			reqd: 1,
		},
		{
			fieldname: "discipline",
			label: __("Discipline"),
			fieldtype: "Link",
			options: "EGC Discipline",
		},
		{
			fieldname: "approval_status",
			label: __("Approval Status"),
			fieldtype: "Select",
			options: [
				"",
				"Not Submitted",
				"Under Review",
				"Approved",
				"Approved with Comments",
				"Revise & Resubmit",
				"Rejected",
			].join("\n"),
		},
		{
			fieldname: "document_type",
			label: __("Document Type"),
			fieldtype: "Link",
			options: "EGC Document Type",
			get_query: () => ({ filters: { is_drawing: 1 } }),
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		// Frappe's datatable invokes the formatter for rows that carry no data object (the
		// placeholder/total rows). Dereferencing `data` there throws, and a throw inside the
		// formatter leaves the whole table rendered as an empty skeleton.
		if (!data) return value;
		if (column.fieldname === "approval_status" && data.approval_status) {
			const colors = {
				Approved: "green",
				"Approved with Comments": "green",
				"Under Review": "orange",
				"Revise & Resubmit": "red",
				Rejected: "red",
				"Not Submitted": "gray",
			};
			const color = colors[data.approval_status] || "gray";
			value = `<span class="indicator-pill ${color}">${data.approval_status}</span>`;
		}
		return value;
	},
};
