import { createApp } from "vue";
import EgcProjectHub from "./EgcProjectHub.vue";
import { syncRouteFromBrowser } from "./composables/useHubRoute";

class EGCProjectHub {
	constructor({ wrapper, page }) {
		this.$wrapper = $(wrapper);
		this.page = page;
		this.init();
	}

	init() {
		this.page.set_title(__("Project Manager"));
		this.setup_app();
	}

	setup_app() {
		let app = createApp(EgcProjectHub, { page: this.page });
		SetVueGlobals(app);
		this.$hub = app.mount(this.$wrapper.get(0));
	}

	// Called by egc_project_hub.js on every route change instead of remounting the app.
	sync_route() {
		syncRouteFromBrowser();
	}
}

frappe.provide("frappe.ui");
frappe.ui.EGCProjectHub = EGCProjectHub;
export default EGCProjectHub;
