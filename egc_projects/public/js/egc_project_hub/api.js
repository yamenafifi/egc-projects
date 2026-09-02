// Thin wrapper around egc_projects.api.hub.* (docs/ARCHITECTURE.md §5). The Hub never queries
// DocTypes directly; every server round trip goes through here so error handling is uniform.

import { extract_message } from "./composables/useFrappeCall";

const HUB_MODULE = "egc_projects.api.hub";

function call_hub(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: `${HUB_MODULE}.${method}`,
			args,
			silent: true,
			callback: (r) => resolve(r.message),
			error: (r) => reject(new Error(extract_message(r))),
		});
	});
}

export function get_my_projects() {
	return call_hub("get_my_projects", {});
}

// The bare `/app/project-manager` landing dashboard's data source — only ever called for a
// financial-access user (see constants.js's FINANCIAL_ROLES / useHubRoute.js); the server gates
// it identically regardless, this is just avoiding a doomed round trip for everyone else.
export function get_portfolio_overview() {
	return call_hub("get_portfolio_overview", {});
}

export function get_project_context(project) {
	return call_hub("get_project_context", { project });
}

export function get_overview(project) {
	return call_hub("get_overview", { project });
}

export function get_wbs_tree(project) {
	return call_hub("get_wbs_tree", { project });
}

export function get_activities(project, filters) {
	return call_hub("get_activities", { project, filters });
}

export function get_submittals(project, filters) {
	return call_hub("get_submittals", { project, filters });
}

export function get_drawings(project, filters) {
	return call_hub("get_drawings", { project, filters });
}

export function get_document_revisions(document) {
	return call_hub("get_document_revisions", { document });
}

export function get_financials(project) {
	return call_hub("get_financials", { project });
}

export function get_financial_transactions(project, metric) {
	return call_hub("get_financial_transactions", { project, metric });
}

export function get_cost_forecast(project) {
	return call_hub("get_cost_forecast", { project });
}

export function get_cash_flow(project) {
	return call_hub("get_cash_flow", { project });
}

export function get_my_open_items(project) {
	return call_hub("get_my_open_items", { project });
}

// Read-only. The write side (save_project_profile/add_stakeholder/remove_stakeholder/
// add_equipment_item/remove_equipment_item) lives in project_profile.py, not api/hub.py — see
// components/project_profile_api.js.
export function get_project_info(project) {
	return call_hub("get_project_info", { project });
}
