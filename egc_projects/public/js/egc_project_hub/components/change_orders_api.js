// Thin wrapper around egc_projects.api.change_orders.* — mirrors activities_api.js's call_*
// pattern exactly (docs/ARCHITECTURE_V2.md §12's "one wrapper file per domain" convention).

import { extract_message } from "../composables/useFrappeCall";

const CHANGE_ORDERS_MODULE = "egc_projects.api.change_orders";

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
