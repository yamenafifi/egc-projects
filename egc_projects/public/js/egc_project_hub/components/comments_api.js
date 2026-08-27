// Thin wrapper around egc_projects.egc_projects.comments.* — generic comment thread on any EGC
// record, reachable by an external (read-only) account exactly like an internal user since the
// gate is a plain "can you read this record" check, not a doctype role.

const COMMENTS_MODULE = "egc_projects.egc_projects.comments";

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
