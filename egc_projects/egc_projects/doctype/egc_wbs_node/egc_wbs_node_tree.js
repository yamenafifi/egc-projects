frappe.provide("frappe.treeview_settings");

frappe.treeview_settings["EGC WBS Node"] = {
	get_tree_nodes: "egc_projects.egc_projects.doctype.egc_wbs_node.egc_wbs_node.get_children",
	add_tree_node: "egc_projects.egc_projects.doctype.egc_wbs_node.egc_wbs_node.add_node",
	filters: [
		{
			fieldname: "project",
			fieldtype: "Link",
			options: "Project",
			label: __("Project"),
			reqd: 1,
		},
	],
	breadcrumb: "Projects",
	root_label: "All WBS Nodes",
	get_tree_root: false,
	ignore_fields: ["parent_egc_wbs_node"],
	onload: function (me) {
		frappe.treeview_settings["EGC WBS Node"].page = {};
		$.extend(frappe.treeview_settings["EGC WBS Node"].page, me.page);
		me.make_tree();
	},
};
