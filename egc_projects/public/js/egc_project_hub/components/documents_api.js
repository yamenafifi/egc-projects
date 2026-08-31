// Thin wrapper around egc_projects.api.documents.* — mirrors ../api.js's call_hub pattern
// exactly. Kept local to the Documents package rather than merged into the shared api.js:
// several packages are adding their own api/*.py module this wave (Activities, Submittals,
// Drawings, Documents — docs/ARCHITECTURE_V2.md §12), and none of them should have to touch the
// same frontend file at once. A later consolidation pass can merge these once every package
// lands.

import { extract_message } from "../composables/useFrappeCall";

const DOCUMENTS_MODULE = "egc_projects.api.documents";

function call_documents(method, args) {
	return new Promise((resolve, reject) => {
		frappe.call({
			method: `${DOCUMENTS_MODULE}.${method}`,
			args,
			silent: true,
			callback: (r) => resolve(r.message),
			error: (r) => reject(new Error(extract_message(r))),
		});
	});
}

export function get_documents(project, filters) {
	return call_documents("get_documents", { project, filters });
}

export function get_document_detail(document) {
	return call_documents("get_document_detail", { document });
}

export function get_drawing_document_types() {
	return call_documents("get_drawing_document_types", {});
}

export function create_document(args) {
	return call_documents("create_document", args);
}

export function create_document_revision(args) {
	return call_documents("create_document_revision", args);
}

export function submit_document_revision(revision) {
	return call_documents("submit_document_revision", { revision });
}

export function update_revision_readiness(revision, readiness) {
	return call_documents("update_revision_readiness", { revision, readiness });
}
