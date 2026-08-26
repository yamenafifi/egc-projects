// Thin wrapper around egc_projects.api.wbs.* — mirrors documents_api.js/activities_api.js's
// call_hub pattern exactly (docs/ARCHITECTURE_V2.md §12's "one wrapper file per domain"
// convention). Kept local rather than merged into the shared api.js, for the same
// concurrent-edit reason documents_api.js documents.

const WBS_MODULE = "egc_projects.api.wbs";

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

function call_wbs(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: `${WBS_MODULE}.${method}`,
			args,
			silent: true,
			callback: (r) => resolve(r.message),
			error: (r) => reject(new Error(extract_message(r))),
		});
	});
}

export function get_wbs_summary(project) {
	return call_wbs("get_wbs_summary", { project });
}

export function reorder_wbs_nodes(parent, ordered_names) {
	return call_wbs("reorder_wbs_nodes", { parent, ordered_names });
}

export function copy_wbs_branch(source_node, target_parent, project) {
	return call_wbs("copy_wbs_branch", { source_node, target_parent, project });
}

export function bulk_create_wbs_nodes(parent, project, rows) {
	return call_wbs("bulk_create_wbs_nodes", { parent, project, rows });
}

// -- Everything below calls Frappe's own generic client API directly — api/wbs.py's documented
// contract has no create/edit endpoint of its own beyond bulk-create, and this file is still
// the one place the Hub's WBS views should reach through for every WBS-related round trip.

function call_core(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method,
			args,
			freeze: true,
			callback: (r) => resolve(r.message),
			error: (r) => reject(new Error(extract_message(r))),
		});
	});
}

export function create_wbs_node(doc) {
	return call_core("frappe.client.insert", { doc: { doctype: "EGC WBS Node", ...doc } });
}

export function update_wbs_node(name, values) {
	return call_core("frappe.client.set_value", { doctype: "EGC WBS Node", name, fieldname: values });
}
