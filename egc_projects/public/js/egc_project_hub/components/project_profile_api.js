// Thin wrapper around egc_projects.egc_projects.project_profile.* — mostly its write side
// (get_project_info itself stays in ../api.js alongside the rest of api/hub.py's endpoints,
// since it lives there on the server); get_person_info is the one read here because it lives in
// this same Python module, used to preview a Person's directory info live in a dialog.

const PROFILE_MODULE = "egc_projects.egc_projects.project_profile";

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

export function save_project_profile(project, values) {
	return call(`${PROFILE_MODULE}.save_project_profile`, { project, values });
}

export function add_stakeholder(project, values) {
	return call(`${PROFILE_MODULE}.add_stakeholder`, { project, values });
}

export function get_person_info(person) {
	return call(`${PROFILE_MODULE}.get_person_info`, { person });
}

export function remove_stakeholder(project, row_name) {
	return call(`${PROFILE_MODULE}.remove_stakeholder`, { project, row_name });
}

export function add_equipment_item(project, values) {
	return call(`${PROFILE_MODULE}.add_equipment_item`, { project, values });
}

export function remove_equipment_item(project, row_name) {
	return call(`${PROFILE_MODULE}.remove_equipment_item`, { project, row_name });
}
