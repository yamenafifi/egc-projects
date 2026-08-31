// Thin wrapper around egc_projects.egc_projects.comments.* — generic comment thread on any EGC
// record, reachable by an external (read-only) account exactly like an internal user since the
// gate is a plain "can you read this record" check, not a doctype role.

import { extract_message } from "../composables/useFrappeCall";

const COMMENTS_MODULE = "egc_projects.egc_projects.comments";

function call(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method,
			args,
			silent: true,
			callback: (r) => resolve(r.message),
			error: (r) => reject(new Error(extract_message(r))),
		});
	});
}

export function get_comments(reference_doctype, reference_name) {
	return call(`${COMMENTS_MODULE}.get_comments`, { reference_doctype, reference_name });
}

export function add_comment(reference_doctype, reference_name, content) {
	return call(`${COMMENTS_MODULE}.add_comment`, { reference_doctype, reference_name, content });
}
