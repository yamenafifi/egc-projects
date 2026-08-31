// Shared by every `*_api.js` wrapper (`api.js` plus one per domain: activities, assignments,
// change_orders, comments, directory, documents, project_profile, submittals, wbs) — each of
// those files used to carry its own byte-identical copy of `extract_message`, so a fix to error-
// message extraction had to be applied in ten places by hand. The `call_*`/`call_core` wrapper
// functions themselves stay local to each file (they differ in which module they call and
// whether they pass `silent`/`freeze`), only the message-extraction logic is shared here.

export function extract_message(r) {
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
