// Thin wrapper around egc_projects.egc_projects.assignments.* — mirrors activities_api.js's
// call_* pattern exactly (docs/ARCHITECTURE_V2.md §12's "one wrapper file per domain"
// convention).

import { extract_message } from "../composables/useFrappeCall";

const ASSIGNMENTS_MODULE = "egc_projects.egc_projects.assignments";

function call_assignments(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: `${ASSIGNMENTS_MODULE}.${method}`,
			args,
			silent: true,
			callback: (r) => resolve(r.message),
			error: (r) => reject(new Error(extract_message(r))),
		});
	});
}

export function get_assignments_for(parent_doctype, parent_name) {
	return call_assignments("get_assignments_for", { parent_doctype, parent_name });
}

export function add_assignment(parent_doctype, parent_name, assignment_role, person, organization, remarks, is_primary) {
	return call_assignments("add_assignment", {
		parent_doctype,
		parent_name,
		assignment_role,
		person,
		organization,
		remarks,
		is_primary,
	});
}

export function remove_assignment(name) {
	return call_assignments("remove_assignment", { name });
}
