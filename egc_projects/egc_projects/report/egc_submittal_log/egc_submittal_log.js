// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.query_reports["EGC Submittal Log"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			reqd: 1,
		},
		{
			fieldname: "submittal_type",
			label: __("Submittal Type"),
			fieldtype: "Link",
			options: "EGC Submittal Type",
		},
		{
			fieldname: "discipline",
			label: __("Discipline"),
			fieldtype: "Link",
			options: "EGC Discipline",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: [
				"",
				"Draft",
				"Submitted",
				"Under Review",
				"Approved",
				"Approved with Comments",
				"Revise & Resubmit",
				"Rejected",
			],
		},
		{
			fieldname: "overdue_only",
			label: __("Overdue only"),
			fieldtype: "Check",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "submittal_status" && data.submittal_status) {
			const colors = {
				Approved: "green",
				"Approved with Comments": "green",
				Submitted: "blue",
				"Under Review": "orange",
				"Revise & Resubmit": "red",
				Rejected: "red",
				Draft: "gray",
			};
			const color = colors[data.submittal_status] || "gray";
			value = `<span class="indicator-pill ${color}">${data.submittal_status}</span>`;
		}
		if (column.fieldname === "days_overdue" && data.days_overdue > 0) {
			value = `<span style="color: var(--red-600); font-weight: bold">${value}</span>`;
		}
		return value;
	},
};
