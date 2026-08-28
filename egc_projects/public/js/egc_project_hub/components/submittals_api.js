// Thin wrapper around egc_projects.api.submittals.* AND the pre-existing whitelisted lifecycle
// functions that already live in egc_projects.egc_projects.submittal_control (mark_under_review,
// record_response, create_next_revision, apply_workflow_template, add_review_step,
// remove_review_step, record_step_response, get_ball_in_court) — both modules' calls go through
// this one file, since the Hub's Submittal views should reach through a single place for every
// Submittal-related round trip, matching documents_api.js/activities_api.js's convention.

const SUBMITTALS_MODULE = "egc_projects.api.submittals";
const SUBMITTAL_CONTROL_MODULE = "egc_projects.egc_projects.submittal_control";

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

// -- api/submittals.py -------------------------------------------------------------------------

export function create_submittal(project, values) {
	return call(`${SUBMITTALS_MODULE}.create_submittal`, { project, ...values });
}

export function get_submittal_detail(submittal) {
	return call(`${SUBMITTALS_MODULE}.get_submittal_detail`, { submittal });
}

export function get_workflow_templates() {
	return call(`${SUBMITTALS_MODULE}.get_workflow_templates`, {});
}

export function get_workflow_template_detail(template) {
	return call(`${SUBMITTALS_MODULE}.get_workflow_template_detail`, { template });
}

export function create_workflow_template(template_name, steps, description) {
	return call(`${SUBMITTALS_MODULE}.create_workflow_template`, { template_name, steps, description });
}

export function get_my_open_reviews(project) {
	return call(`${SUBMITTALS_MODULE}.get_my_open_reviews`, { project });
}

export function submit_submission(submission) {
	return call(`${SUBMITTALS_MODULE}.submit_submission`, { submission });
}

export function create_first_submission(submittal) {
	return call(`${SUBMITTALS_MODULE}.create_first_submission`, { submittal });
}

export function delete_submittal(submittal) {
	return call(`${SUBMITTALS_MODULE}.delete_submittal`, { submittal });
}

export function get_documents_with_current_revision(project, documents) {
	return call(`${SUBMITTALS_MODULE}.get_documents_with_current_revision`, { project, documents });
}

export function update_submission_dates(submission, dates) {
	return call(`${SUBMITTALS_MODULE}.update_submission_dates`, { submission, ...dates });
}

// -- submittal_control.py (pre-existing lifecycle + v2 step engine) -------------------------

export function mark_under_review(submission) {
	return call(`${SUBMITTAL_CONTROL_MODULE}.mark_under_review`, { submission });
}

export function record_response(submission, response, remarks, response_date) {
	return call(`${SUBMITTAL_CONTROL_MODULE}.record_response`, { submission, response, remarks, response_date });
}

export function create_next_revision(submittal) {
	return call(`${SUBMITTAL_CONTROL_MODULE}.create_next_revision`, { submittal });
}

export function apply_workflow_template(submission, template) {
	return call(`${SUBMITTAL_CONTROL_MODULE}.apply_workflow_template`, { submission, template });
}

export function add_review_step(submission, sequence, reviewer_role, reviewer_user, is_required) {
	return call(`${SUBMITTAL_CONTROL_MODULE}.add_review_step`, {
		submission,
		sequence,
		reviewer_role,
		reviewer_user,
		is_required,
	});
}

export function remove_review_step(step) {
	return call(`${SUBMITTAL_CONTROL_MODULE}.remove_review_step`, { step });
}

export function record_step_response(step, response, remarks, attachment) {
	return call(`${SUBMITTAL_CONTROL_MODULE}.record_step_response`, { step, response, remarks, attachment });
}

export function get_ball_in_court(submission) {
	return call(`${SUBMITTAL_CONTROL_MODULE}.get_ball_in_court`, { submission });
}

export function add_submission_document(submission, document_revision) {
	return call(`${SUBMITTALS_MODULE}.add_submission_document`, { submission, document_revision });
}

export function remove_submission_document(submission, row_name) {
	return call(`${SUBMITTALS_MODULE}.remove_submission_document`, { submission, row_name });
}
