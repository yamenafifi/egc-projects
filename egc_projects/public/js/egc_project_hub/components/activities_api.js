// Thin wrapper around egc_projects.api.activities.* — mirrors documents_api.js's call_hub
// pattern exactly (docs/ARCHITECTURE_V2.md §12's "one wrapper file per domain" convention).
// Kept local to the Activities/Schedule package rather than merged into the shared api.js, for
// the same concurrent-edit reason documents_api.js documents.

import { extract_message } from "../composables/useFrappeCall";

const ACTIVITIES_MODULE = "egc_projects.api.activities";

function call_activities(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: `${ACTIVITIES_MODULE}.${method}`,
			args,
			silent: true,
			callback: (r) => resolve(r.message),
			error: (r) => reject(new Error(extract_message(r))),
		});
	});
}

export function get_activity_detail(activity) {
	return call_activities("get_activity_detail", { activity });
}

export function get_activity_gantt_rows(project) {
	return call_activities("get_activity_gantt_rows", { project });
}

export function add_dependency(predecessor, successor, dependency_type, lag_days) {
	return call_activities("add_dependency", { predecessor, successor, dependency_type, lag_days });
}

export function remove_dependency(name) {
	return call_activities("remove_dependency", { name });
}

export function update_activity_progress(activity, percent_complete, status) {
	return call_activities("update_activity_progress", { activity, percent_complete, status });
}

export function get_activity_history(activity) {
	return call_activities("get_activity_history", { activity });
}

export function create_child_activity(parent, values) {
	return call_activities("create_child_activity", { parent, ...values });
}

// -- Everything below calls Frappe's own generic client API, or the pre-existing (not owned by
// this wave's Activities package) `relationships.py` module, directly — `api/activities.py`'s
// documented contract has no field-edit/link endpoints of its own beyond `create_child_activity`
// above, and this file is still the one place the Hub's Activity views should reach through for
// every Activity-related round trip. `create_activity` below is only ever for a ROOT Activity
// (no parent to possibly flip into a group) — anything creating a CHILD must go through
// `create_child_activity` instead, never this generic insert.

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

export function create_activity(doc) {
	return call_core("frappe.client.insert", { doc: { doctype: "EGC Activity", ...doc } });
}

export function update_activity_fields(name, values) {
	return call_core("frappe.client.set_value", { doctype: "EGC Activity", name, fieldname: values });
}

const RELATIONSHIPS_MODULE = "egc_projects.egc_projects.relationships";

export function link_activity_record(activity, link_doctype, link_name, link_purpose, remarks) {
	return call_core(`${RELATIONSHIPS_MODULE}.add_link`, {
		activity,
		link_doctype,
		link_name,
		link_purpose,
		remarks,
	});
}

export function unlink_activity_record(name) {
	return call_core(`${RELATIONSHIPS_MODULE}.remove_link`, { name });
}
