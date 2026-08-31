// Thin wrapper around egc_projects.api.bulk_transfer.* — mirrors every other `*_api.js`'s
// convention, except `download_export_template`: a real file download can't go through
// `frappe.call()` (a JSON-mode XHR has no way to trigger the browser's save dialog), so it
// replicates the exact hidden-form-POST pattern Frappe's OWN List View "Export" button and Data
// Import "Download Template" button already use (`open_url_post`, a global helper the Desk app
// loads — see apps/frappe/frappe/public/js/frappe/utils/urllib.js and reportview.js's own
// `export_query` call site, which this mirrors 1:1: `cmd` posted to "/" is the classic Frappe RPC
// dispatch, same as every other exporter in core).

import { extract_message } from "../composables/useFrappeCall";

const BULK_TRANSFER_MODULE = "egc_projects.api.bulk_transfer";

function call(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: `${BULK_TRANSFER_MODULE}.${method}`,
			args,
			freeze: true,
			callback: (r) => resolve(r.message),
			error: (r) => reject(new Error(extract_message(r))),
		});
	});
}

export function download_export_template(project, doctype, file_type, with_data, names) {
	open_url_post("/", {
		cmd: `${BULK_TRANSFER_MODULE}.get_export_template`,
		project,
		doctype,
		file_type,
		with_data: with_data ? 1 : 0,
		...(names && names.length ? { names: JSON.stringify(names) } : {}),
	});
}

export function import_records(project, doctype, file_url, update_existing, send_email) {
	return call("import_records", {
		project,
		doctype,
		file_url,
		update_existing: update_existing ? 1 : 0,
		send_email: send_email ? 1 : 0,
	});
}

export function delete_records(project, doctype, names) {
	return call("delete_records", { project, doctype, names: JSON.stringify(names) });
}
