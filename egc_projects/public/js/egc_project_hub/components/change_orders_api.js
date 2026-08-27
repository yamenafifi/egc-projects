// Thin wrapper around egc_projects.api.change_orders.* — mirrors activities_api.js's call_*
// pattern exactly (docs/ARCHITECTURE_V2.md §12's "one wrapper file per domain" convention).

const CHANGE_ORDERS_MODULE = "egc_projects.api.change_orders";

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

function call_change_orders(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: `${CHANGE_ORDERS_MODULE}.${method}`,
			args,
			silent: true,
			callback: (r) => resolve(r.message),
			error: (r) => reject(new Error(extract_message(r))),
		});
	});
}

export function get_contract_value_breakdown(project) {
	return call_change_orders("get_contract_value_breakdown", { project });
}

export function get_change_orders(project, status) {
	return call_change_orders("get_change_orders", { project, status });
}
