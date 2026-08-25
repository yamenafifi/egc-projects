// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.query_reports["EGC Activity Status Summary"] = {
	filters: [
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
			reqd: 1,
		},
		{
			fieldname: "wbs_node",
			label: __("WBS Node"),
			fieldtype: "Link",
			options: "EGC WBS Node",
			get_query() {
				const project = frappe.query_report.get_filter_value("project");
				return { filters: project ? { project } : {} };
			},
		},
		{
			fieldname: "discipline",
			label: __("Discipline"),
			fieldtype: "Link",
			options: "EGC Discipline",
			get_query() {
				return { filters: { enabled: 1 } };
			},
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: ["", "Not Started", "In Progress", "On Hold", "Completed", "Cancelled"].join("\n"),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (column.fieldname === "status" && data) {
			const colors = {
				"Not Started": "gray",
				"In Progress": "blue",
				"On Hold": "orange",
				Completed: "green",
				Cancelled: "red",
			};
			value = `<span class="indicator-pill ${colors[data.status] || "gray"}">${__(data.status || "")}</span>`;
		}

		// An overdue row is the thing a project manager is scanning for, so give the date
		// itself the warning colour rather than relying on the separate Overdue column.
		if (column.fieldname === "planned_end_date" && data && data.is_overdue) {
			value = `<span style="color: var(--red-500); font-weight: 500;">${value}</span>`;
		}

		return value;
	},

	// The report is returned in tree order with an `indent` per row; this makes the tree
	// collapsible rather than merely indented.
	tree: true,
	name_field: "name",
	parent_field: "parent_egc_activity",
	initial_depth: 3,
};
