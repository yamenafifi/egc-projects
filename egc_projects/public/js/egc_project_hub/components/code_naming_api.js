// Thin wrapper around egc_projects.egc_projects.code_naming.* — the three whitelisted "peek"
// functions dialogs call live as Discipline/Type is picked (see code_naming.py for why these
// never mutate the underlying Series counter).

import { extract_message } from "../composables/useFrappeCall";

const CODE_NAMING_MODULE = "egc_projects.egc_projects.code_naming";

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

export function suggest_activity_code(project, discipline) {
	return call(`${CODE_NAMING_MODULE}.suggest_activity_code`, { project, discipline });
}

export function suggest_document_code(project, discipline, document_type) {
	return call(`${CODE_NAMING_MODULE}.suggest_document_code`, { project, discipline, document_type });
}

export function suggest_submittal_code(project, discipline, submittal_type) {
	return call(`${CODE_NAMING_MODULE}.suggest_submittal_code`, { project, discipline, submittal_type });
}
