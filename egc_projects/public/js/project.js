// Entry point from the standard ERPNext Project form into the EGC Project Hub.
//
// This is deliberately a client extension rather than a custom field: nothing is written into
// the core Project schema, so the ERPNext upgrade surface stays at zero.

frappe.ui.form.on("Project", {
	refresh(frm) {
		if (frm.is_new()) return;

		// The one way into the Hub from here — WBS/Activities/Drawing Register/Submittal Log
		// used to also get their own shortcuts in a second "EGC Projects" dropdown, redundant
		// now that the Hub itself has a tab for every one of them (and a Directory tab besides);
		// removed rather than left as a second, easy-to-miss path to the same places.
		frm.add_custom_button(
			__("Open in Project Manager"),
			() => frappe.set_route("project-manager", frm.doc.name),
			null
		);

		// `Address` has no direct FK to `Project` (core's own Dynamic Link pattern — see
		// project_profile.py's get_addresses_for_project) — only offer Addresses already
		// linked to THIS project rather than every Address in the system.
		frm.set_query("custom_project_address", () => ({
			query: "egc_projects.egc_projects.project_profile.get_addresses_for_project",
			filters: { project: frm.doc.name },
		}));

		// Without this, "Create a new Address" from the field above opens Address's own full
		// form with no idea which Project it's for — the new record would save unlinked, fail
		// the very filter that field just used, and appear to have vanished. Pre-filling the
		// Dynamic Link row here means it's born already linked, the same "create new -> route
		// options" mechanism `frappe.ui.form.ControlLink` already supports for any Link field
		// (see e.g. erpnext/selling/doctype/quotation/quotation.js's own use of this).
		const address_field = frm.get_field("custom_project_address");
		if (address_field) {
			address_field.df.get_route_options_for_new_doc = () => ({
				links: [{ link_doctype: "Project", link_name: frm.doc.name }],
			});
		}
	},
	custom_project_address(frm) {
		// Covers both picking an existing (already-linked) Address and creating a brand new
		// one via this field's own quick-entry, which has no way to know about Project on its
		// own — see project_profile.ensure_address_linked_to_project for why this is idempotent.
		if (!frm.doc.custom_project_address) return;
		frappe.call({
			method: "egc_projects.egc_projects.project_profile.ensure_address_linked_to_project",
			args: { address: frm.doc.custom_project_address, project: frm.doc.name },
		});
	},
});
