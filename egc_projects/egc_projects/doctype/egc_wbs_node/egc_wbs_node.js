frappe.ui.form.on("EGC WBS Node", {
	setup(frm) {
		// UX filtering only — the same rules are enforced server-side by
		// egc_projects.validators.validate_tree_parent (docs/ARCHITECTURE.md §0.5).
		frm.set_query("parent_egc_wbs_node", function () {
			return {
				filters: {
					project: frm.doc.project,
					is_group: 1,
					name: ["!=", frm.doc.name],
				},
			};
		});

		frm.set_query("discipline", function () {
			return {
				filters: {
					enabled: 1,
				},
			};
		});
	},
});
