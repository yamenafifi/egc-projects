// Thin wrapper around egc_projects.api.documents.* — mirrors ../api.js's call_hub pattern
// exactly. Kept local to the Documents package rather than merged into the shared api.js:
// several packages are adding their own api/*.py module this wave (Activities, Submittals,
// Drawings, Documents — docs/ARCHITECTURE_V2.md §12), and none of them should have to touch the
// same frontend file at once. A later consolidation pass can merge these once every package
// lands.

const DOCUMENTS_MODULE = "egc_projects.api.documents";

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
