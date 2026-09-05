// Thin wrapper around egc_projects.api.directory.* — mirrors activities_api.js's call pattern.

import { extract_message } from "../composables/useFrappeCall";

const DIRECTORY_MODULE = "egc_projects.api.directory";

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

export function grant_portal_access(project, row_name, email) {
	return call(`${DIRECTORY_MODULE}.grant_portal_access`, { project, row_name, email });
}

export function revoke_portal_access(project, user) {
	return call(`${DIRECTORY_MODULE}.revoke_portal_access`, { project, user });
}

export function update_stakeholder_role(project, row_name, role) {
	return call(`${DIRECTORY_MODULE}.update_stakeholder_role`, { project, row_name, role });
}

export function get_person_profile(project, row_name) {
	return call(`${DIRECTORY_MODULE}.get_person_profile`, { project, row_name });
}
