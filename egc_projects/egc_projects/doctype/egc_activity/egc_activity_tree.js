// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.provide("frappe.treeview_settings");

const EGC_ACTIVITY_STATUS_COLORS = {
	"Not Started": "grey",
	"In Progress": "blue",
	"On Hold": "orange",
	Completed: "green",
	Cancelled: "dark-grey",
};

frappe.treeview_settings["EGC Activity"] = {
	breadcrumb: "EGC Projects",
	root_label: "All Activities",
	get_tree_root: false,
	get_tree_nodes: "egc_projects.egc_projects.doctype.egc_activity.egc_activity.get_children",
	add_tree_node: "egc_projects.egc_projects.doctype.egc_activity.egc_activity.add_node",
	ignore_fields: ["parent_egc_activity"],

	filters: [
		{
			fieldname: "project",
			fieldtype: "Link",
			options: "Project",
			label: __("Project"),
			reqd: 1,
		},
		{
			fieldname: "wbs_node",
			fieldtype: "Link",
			options: "EGC WBS Node",
			label: __("WBS Node"),
			get_query: function () {
				const me = frappe.treeview_settings["EGC Activity"];
				const project = me.page.fields_dict.project.get_value();
				return { filters: { project: project || "" } };
			},
		},
	],

	// Fields collected by the tree's own "New" dialog; the parent/project are forced server-side
	// by add_node(), not editable here (see ignore_fields above).
	fields: [
		{
			fieldtype: "Data",
			fieldname: "activity_code",
			label: __("Activity Code"),
			reqd: 1,
		},
		{
			fieldtype: "Data",
			fieldname: "activity_name",
			label: __("Activity Name"),
			reqd: 1,
		},
		{
			fieldtype: "Check",
			fieldname: "is_group",
			label: __("Is Group"),
		},
		{
			fieldtype: "Link",
			fieldname: "wbs_node",
			label: __("WBS Node"),
			options: "EGC WBS Node",
		},
		{
			fieldtype: "Link",
			fieldname: "discipline",
			label: __("Discipline"),
			options: "EGC Discipline",
		},
	],

	get_label: function (node) {
		const data = node.data || {};
		const label =
			data.activity_code && data.activity_name
				? `${data.activity_code}: ${data.activity_name}`
				: node.title || node.label;
		const color = EGC_ACTIVITY_STATUS_COLORS[data.status] || "grey";
		return `<span class="indicator ${color}"></span>${frappe.utils.escape_html(__(label))}`;
	},

	onload: function (treeview) {
		// Mirrors erpnext's task_tree.js: stash the page so filters' get_query closures (like
		// wbs_node above) can read the live Project filter value.
		frappe.treeview_settings["EGC Activity"].page = {};
		$.extend(frappe.treeview_settings["EGC Activity"].page, treeview.page);
	},
};
