// Thin wrapper around egc_projects.api.directory.* — mirrors activities_api.js's call pattern.

const DIRECTORY_MODULE = "egc_projects.api.directory";

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

export function get_directory(project) {
	return call(`${DIRECTORY_MODULE}.get_directory`, { project });
}

export function grant_portal_access(project, row_name, role, email) {
	return call(`${DIRECTORY_MODULE}.grant_portal_access`, { project, row_name, role, email });
}

export function revoke_portal_access(project, user) {
	return call(`${DIRECTORY_MODULE}.revoke_portal_access`, { project, user });
}

export function update_stakeholder_role(project, row_name, role) {
	return call(`${DIRECTORY_MODULE}.update_stakeholder_role`, { project, row_name, role });
}
