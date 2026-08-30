// Route is the single source of truth for "which project / which tab" (docs/ARCHITECTURE.md
// §5): /app/egc-project-hub/<project>/<tab>. Module-level state because only one Hub instance
// is ever mounted at a time, and the egc_project_hub.js loader re-syncs the same instance on
// every internal route change rather than remounting.

import { reactive, readonly } from "vue";

// "documents" (Documents register) and "project-info" (Project Information) were added in
// WP-11 alongside the WP-10/WP-09 packages that own their tab content. Order here drives
// HubTopBar's Toolbox menu order via EgcProjectHub.vue's tab_defs.
//
// "drawings" was removed as a separate tab — a Drawing is just an EGC Project Document whose
// Document Type has is_drawing=1, not a distinct record type, so it never needed a second
// register with its own parallel create-dialog and filter bar. DocumentsTab.vue's "Drawings
// only" toggle covers the same ground now; a bare "drawings" tab in an old bookmark/localStorage
// falls through to DEFAULT_TAB via the TABS.includes() guard in read_route() below.
export const TABS = [
	"overview",
	"wbs",
	"activities",
	"submittals",
	"documents",
	"directory",
	"financials",
	"project-info",
];
const DEFAULT_TAB = TABS[0];
const STORAGE_KEY = "egc_project_hub:last_project";

const state = reactive({ project: null, tab: DEFAULT_TAB });
let restoring = false;

function read_route() {
	const route = frappe.get_route();
	const project = route[1] || null;
	const raw_tab = route[2] || DEFAULT_TAB;
	const tab = TABS.includes(raw_tab) ? raw_tab : DEFAULT_TAB;
	return { project, tab };
}

export function syncRouteFromBrowser() {
	// frappe.router fires "change" for every Desk navigation, not just ones inside the Hub —
	// e.g. clicking a table row sets the route to ["Form", "EGC Activity", name]. Reacting to
	// that would misread "EGC Activity" as the project and clobber state/localStorage.
	if (frappe.get_route()[0] !== "egc-project-hub") return;

	const { project, tab } = read_route();

	if (!project && !restoring) {
		const last_project = localStorage.getItem(STORAGE_KEY);
		if (last_project) {
			restoring = true;
			frappe.set_route("egc-project-hub", last_project, tab);
			return;
		}
	}
	restoring = false;

	state.project = project;
	state.tab = tab;
	if (project) localStorage.setItem(STORAGE_KEY, project);
}

let listening = false;

export function useHubRoute() {
	if (!listening) {
		frappe.router.on("change", syncRouteFromBrowser);
		listening = true;
		syncRouteFromBrowser();
	}

	function setProject(project) {
		if (!project) return;
		frappe.set_route("egc-project-hub", project, state.tab || DEFAULT_TAB);
	}

	function setTab(tab) {
		if (!state.project || !TABS.includes(tab)) return;
		frappe.set_route("egc-project-hub", state.project, tab);
	}

	function clearProject() {
		localStorage.removeItem(STORAGE_KEY);
		state.project = null;
		frappe.set_route("egc-project-hub");
	}

	return { route: readonly(state), setProject, setTab, clearProject };
}
