// Entry point from the standard ERPNext Project form into the EGC Project Hub.
//
// This is deliberately a client extension rather than a custom field: nothing is written into
// the core Project schema, so the ERPNext upgrade surface stays at zero.

frappe.ui.form.on("Project", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(
			__("Open in EGC Projects"),
			() => frappe.set_route("egc-project-hub", frm.doc.name),
			null
		);

		frm.add_custom_button(
			__("WBS"),
			() => frappe.set_route("Tree", "EGC WBS Node", { project: frm.doc.name }),
			__("EGC Projects")
		);
		frm.add_custom_button(
			__("Activities"),
			() => frappe.set_route("Tree", "EGC Activity", { project: frm.doc.name }),
			__("EGC Projects")
		);
		frm.add_custom_button(
			__("Drawing Register"),
			() =>
				frappe.set_route("query-report", "EGC Drawing Register", {
					project: frm.doc.name,
				}),
			__("EGC Projects")
		);
		frm.add_custom_button(
			__("Submittal Log"),
			() =>
				frappe.set_route("query-report", "EGC Submittal Log", {
					project: frm.doc.name,
				}),
			__("EGC Projects")
		);
	},
});
