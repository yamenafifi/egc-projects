// This page kept its old identity ("egc-project-hub") purely as a redirect — the Hub itself
// moved to /app/project-manager (project_manager.json/.js). Old links already sent (ball-in-court
// review emails, Directory welcome emails) still work; nothing here mounts the Vue app.
frappe.pages["egc-project-hub"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, single_column: true });
};

frappe.pages["egc-project-hub"].on_page_show = function () {
	const [, ...rest] = frappe.get_route();
	frappe.set_route("project-manager", ...rest.filter(Boolean));
};
