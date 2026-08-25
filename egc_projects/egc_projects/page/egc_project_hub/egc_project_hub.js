frappe.pages["egc-project-hub"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("EGC Project Hub"),
		single_column: true,
	});

	// hot reload in development
	if (frappe.boot.developer_mode) {
		frappe.hot_update = frappe.hot_update || [];
		frappe.hot_update.push(() => load_egc_project_hub(wrapper));
	}
};

frappe.pages["egc-project-hub"].on_page_show = function (wrapper) {
	load_egc_project_hub(wrapper);
};

function load_egc_project_hub(wrapper) {
	frappe.require("egc_project_hub.bundle.js").then(() => {
		// on_page_show fires on every internal route change (tab/project switch), so reuse the
		// live instance instead of tearing down and remounting the Vue app each time.
		if (frappe.egc_project_hub && frappe.egc_project_hub.wrapper === wrapper) {
			frappe.egc_project_hub.sync_route();
			return;
		}

		let $parent = $(wrapper).find(".layout-main-section");
		$parent.empty();
		frappe.egc_project_hub = new frappe.ui.EGCProjectHub({
			wrapper: $parent,
			page: wrapper.page,
		});
		frappe.egc_project_hub.wrapper = wrapper;
	});
}
