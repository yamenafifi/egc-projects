// Thin wrapper around egc_projects.api.hub.* (docs/ARCHITECTURE.md §5). The Hub never queries
// DocTypes directly; every server round trip goes through here so error handling is uniform.

const HUB_MODULE = "egc_projects.api.hub";

function extract_message(r) {
	if (r && r._server_messages) {
		try {
			const messages = JSON.parse(r._server_messages);
			const first = JSON.parse(messages[0]);
			if (first && first.message) return first.message;
		} catch (e) {
			// fall through to other extraction strategies
		}
	}
	if (r && r.exc) {
		try {
			const exc_list = JSON.parse(r.exc);
			const last_line = exc_list[0].trim().split("\n").pop();
			return last_line.replace(/^[\w.]+Error:\s*/, "");
		} catch (e) {
			// fall through
		}
	}
	return __("Something went wrong. Please try again.");
}

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

export function get_my_open_items(project) {
	return call_hub("get_my_open_items", { project });
}

// No save_project_info: Project Information is edited on the native `Project` form now
// (custom_egc_* fields, see project_custom_fields.py), never through the Hub.
export function get_project_info(project) {
	return call_hub("get_project_info", { project });
}
