<!-- Submittal detail workspace — a full-page view that REPLACES the Submittals tab's list
     (SubmittalsTab.vue swaps the list out for this, it doesn't overlay it — see that file's
     `selected_submittal` branch). Modeled on a GitHub pull request page: a status banner up top
     for "what's true right now and what to do about it", a single chronological timeline down
     the middle for "everything that has happened" (every cycle started, submitted, and responded
     to, comments interleaved by real timestamp), and a sidebar for the standing facts that don't
     belong in a history feed (documents, reviewers still pending, team, dates).

     Shows EVERY submission cycle, not just the current one — "confirm full history remains
     visible" is one of the build brief's own acceptance checks, and a Revise & Resubmit cycle is
     exactly the case where hiding history would be actively misleading. -->
<script setup>
import { computed, ref, watch } from "vue";
import {
	get_submittal_detail,
	submit_submission,
	create_next_revision,
	apply_workflow_template,
	get_workflow_templates,
	get_workflow_template_detail,
	record_step_response,
	add_submission_document,
	remove_submission_document,
	add_review_step,
	remove_review_step,
	delete_submittal,
	update_submission_dates,
} from "./submittals_api";
import { openSubmitForReviewFlow } from "./submit_for_review_flow";
import { renderStagesPreviewHtml } from "./workflow_template_flow";
import { get_directory_person_emails, person_link_filter } from "./directory_helpers";
import { link_activity_record, unlink_activity_record } from "./activities_api";
import { add_assignment, remove_assignment } from "./assignments_api";
import { get_person_info } from "./project_profile_api";
import { get_comments, add_comment } from "./comments_api";
import { useHubRoute } from "../composables/useHubRoute";
import { openDocumentIntent } from "../composables/useOpenDocumentIntent";
import { openActivityIntent } from "../composables/useOpenActivityIntent";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";
import WorkflowStepper from "./WorkflowStepper.vue";

const props = defineProps({
	submittal: { type: String, required: true },
	project: { type: String, required: true },
	canWrite: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "changed"]);

const { data, loading, error, reload } = useHubResource(() => get_submittal_detail(props.submittal));
watch(() => props.submittal, reload, { immediate: true });

function notify_changed() {
	emit("changed");
	reload();
}

function open_form() {
	frappe.set_route("Form", "EGC Submittal", props.submittal);
}

const { setTab } = useHubRoute();

function open_activity(name) {
	// Into the Hub's own ActivitiesTab/ActivityFullPage, not the raw native form — same reasoning
	// as open_document() just below.
	openActivityIntent.activity = name;
	setTab("activities");
}

function open_document(name) {
	// Into the Hub's own DocumentsTab/DocumentDetail, not the raw native form — Documents and
	// Submittals should be able to cross-navigate into each other's rich Hub view, not just the
	// plain Frappe form (docs/ARCHITECTURE_V2.md's Documents/Submittals redesign).
	openDocumentIntent.document = name;
	setTab("documents");
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

function format_datetime(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

// The current cycle is always the FIRST row — submissions are returned newest-first
// (submission_seq desc), matching the register's own "current" convention.
const current_submission = computed(() => (data.value?.submissions || [])[0] || null);

const has_steps = computed(() => (current_submission.value?.steps || []).length > 0);
const stages = computed(() => {
	const steps = current_submission.value?.steps || [];
	const by_sequence = {};
	for (const step of steps) {
		(by_sequence[step.sequence] = by_sequence[step.sequence] || []).push(step);
	}
	return Object.keys(by_sequence)
		.map(Number)
		.sort((a, b) => a - b)
		.map((seq) => ({ sequence: seq, steps: by_sequence[seq] }));
});

// -- delete: only ever offered while every cycle is still Draft — once a submittal has real
// review history, that history is permanent (submittals_api.delete_submittal enforces this
// server-side too; this just avoids showing an action that would only fail). ---------------------

const has_submitted_history = computed(() => (data.value?.submissions || []).some((s) => s.docstatus !== 0));

async function confirm_delete_submittal() {
	frappe.confirm(__("Delete this submittal? This cannot be undone."), () => {
		delete_submittal(props.submittal)
			.then(() => {
				emit("changed");
				emit("close");
			})
			.catch((e) => {
				frappe.msgprint({ title: __("Could Not Delete"), message: e.message, indicator: "red" });
			});
	});
}

// -- one-line "what's going on / what's next" summary, shown in the banner right under the title -

const RESPONSE_IS_FINAL_OK = ["Approved", "Approved with Comments"];

function response_tone(response) {
	if (RESPONSE_IS_FINAL_OK.includes(response)) return "green";
	if (response === "Rejected") return "red";
	if (response === "Revise & Resubmit") return "orange";
	return "grey";
}

const ball_in_court = computed(() => data.value?.submittal?.ball_in_court);

const banner_tone = computed(() => {
	const s = current_submission.value;
	if (!s) return "grey";
	if (s.submission_status === "Responded") return response_tone(s.response);
	if (s.docstatus === 0) return "grey";
	return "blue";
});

// -- tracked documents: the document(s) this submittal is actually about, at their LIVE latest
// issued revision — not frozen to whatever a given cycle happened to attach. Flags when the
// current cycle's own attached revision has fallen behind. ---------------------------------------

const tracked_documents_display = computed(() => {
	const current_doc_revisions = new Set((current_submission.value?.documents || []).map((d) => d.document_revision));
	return (data.value?.tracked_documents || []).map((doc) => ({
		...doc,
		is_current_in_this_cycle: current_doc_revisions.has(doc.current_revision),
	}));
});

const next_step_text = computed(() => {
	const s = current_submission.value;
	if (!s) return null;

	if (s.submission_status === "Responded") {
		if (RESPONSE_IS_FINAL_OK.includes(s.response)) {
			return __("{0} — no action needed.", [s.response]);
		}
		// ball_in_court, once Responded, is only ever non-empty here because
		// submittal_control.py found a Responsible owner for the fix — see the "resubmission
		// needed" suffix it appends. When nobody's marked Responsible yet, fall back to the
		// generic prompt instead of implying a reassignable owner that doesn't exist.
		return ball_in_court.value
			? __("{0} — {1}. Reassign it in Team below if it should be someone else's.", [s.response, ball_in_court.value])
			: __("{0} — ready to resubmit once it's fixed.", [s.response]);
	}

	if (ball_in_court.value) {
		return __("Waiting on {0} to respond.", [ball_in_court.value]);
	}

	if (s.docstatus === 0) {
		return s.documents.length
			? __("Draft — ready to submit for review, or add more reviewers/documents first.")
			: __("Draft — add at least one document revision, then submit for review.");
	}

	// Reachable only for a pre-existing submission with no formal review steps at all (created
	// before every Submittal went through the reviewer workflow, or via the raw native form) —
	// every new submission now always has at least one step, so this has no in-Hub action any
	// more; record its outcome from the native EGC Submittal Revision form instead.
	return __("{0} — no formal review steps on this cycle. Record its outcome from the native Submittal Revision form.", [
		s.submission_status,
	]);
});

// The actual reason behind a Rejected/Revise & Resubmit response, surfaced prominently in the
// banner instead of only living on whichever individual reviewer step caused it (or, for the
// no-steps path, nowhere in the UI at all — it was captured in the database and simply never
// displayed). It also appears in its own place in the timeline below, in context.
const rejection_reason_text = computed(() => {
	const s = current_submission.value;
	if (!s || s.submission_status !== "Responded" || RESPONSE_IS_FINAL_OK.includes(s.response)) return null;
	return s.response_remarks || null;
});

const current_user = frappe.session.user;

// Mirrors submittal_control.py's `_is_step_override_user()` exactly: an internal user holding
// one of these roles may record a response on ANY reviewer's step, not only their own — e.g. an
// external reviewer emailed their decision in and a PM/Document Controller enters it for them.
const STEP_OVERRIDE_ROLES = ["System Manager", "EGC Project Manager", "EGC Document Controller"];
const is_step_override_user = computed(() => (frappe.user_roles || []).some((role) => STEP_OVERRIDE_ROLES.includes(role)));

function can_respond_to(step) {
	if (step.status !== "In Review") return false;
	return step.reviewer_user === current_user || is_step_override_user.value;
}

// -- submit / record a reviewer's response on their step ------------------------------------

const submitting = ref(false);

async function do_submit() {
	submitting.value = true;
	try {
		await submit_submission(current_submission.value.name);
		notify_changed();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Submit"), message: e.message, indicator: "red" });
	} finally {
		submitting.value = false;
	}
}

const RESPONSES = ["Approved", "Approved with Comments", "Revise & Resubmit", "Rejected"];
const TERMINAL_RESPONSES = ["Rejected", "Revise & Resubmit"];

// A step may only forward live when it's the SOLE active required reviewer of its own stage —
// with several required reviewers in parallel, there's no single "next" for one of them to hand
// off to on the others' behalf (submittal_control.py's own `record_step_response` enforces this
// same rule server-side; this is just what decides whether to show the control at all).
function _is_sole_active_required_step(step) {
	const siblings = current_submission.value?.steps || [];
	return !siblings.some(
		(s) => s.name !== step.name && s.sequence === step.sequence && s.status === "In Review" && s.is_required
	);
}

// The pre-planned reviewer this step's stage would otherwise open next, if any — shown as the
// live "Forward to" field's own default, so accepting it with no changes reproduces exactly
// today's automatic behavior (zero added friction for the common, non-rerouted case).
function _default_next_reviewer() {
	const pending = (current_submission.value?.steps || [])
		.filter((s) => s.status === "Pending")
		.sort((a, b) => a.sequence - b.sequence);
	if (!pending.length) return null;
	return { user: pending[0].reviewer_user, label: pending[0].reviewer_label || pending[0].reviewer_role };
}

// What the sidebar's reviewer row shows inline, next to a currently-active step — visible before
// anyone has to open the Respond dialog at all, per "make information readily present."
function next_reviewer_hint(step) {
	if (step.status !== "In Review" || !_is_sole_active_required_step(step)) return null;
	const next = _default_next_reviewer();
	return next ? next.label || next.user : null;
}

async function open_record_response_dialog(step) {
	const forwardable = _is_sole_active_required_step(step);
	const default_next = forwardable ? _default_next_reviewer() : null;
	const directory_emails = forwardable ? await get_directory_person_emails(props.project) : [];

	const fields = [
		{ fieldname: "response", fieldtype: "Select", label: __("Response"), options: RESPONSES, reqd: 1 },
		{
			fieldname: "remarks",
			fieldtype: "Small Text",
			label: __("Remarks"),
			// Required specifically for Rejected/Revise & Resubmit — approving with nothing to
			// say is fine, but sending something back with no reason leaves whoever inherits the
			// resubmission with nothing to act on.
			mandatory_depends_on: 'eval:["Rejected", "Revise & Resubmit"].includes(doc.response)',
			description: __("Required when rejecting or requesting a revision — this is what shows as the reason."),
		},
		{
			fieldname: "attachment",
			fieldtype: "Attach",
			label: __("Attachment"),
			description: __("Optional — a marked-up file you're returning with your response (e.g. an annotated drawing)."),
			options: { doctype: "EGC Submittal Review Step", docname: step.name, fieldname: "response_attachment", folder: `Home/Projects/${props.project}/Submittals` },
		},
	];

	if (forwardable) {
		fields.push(
			{
				fieldtype: "Section Break",
				label: __("Forward To"),
				depends_on: `eval:!${JSON.stringify(TERMINAL_RESPONSES)}.includes(doc.response)`,
			},
			{
				fieldname: "forward_to_user",
				fieldtype: "Link",
				label: __("Next Reviewer"),
				options: "User",
				default: default_next?.user || undefined,
				description: default_next
					? __("Defaults to {0}, the next planned reviewer — pick someone else to route there instead, or clear this to leave it unset.", [default_next.label || default_next.user])
					: __("Nothing is planned after this — pick someone to route it to, or leave blank if this response is final."),
				get_query: person_link_filter(directory_emails),
			}
		);
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Record Response"),
		fields,
		primary_action_label: __("Record"),
		primary_action(values) {
			const forward_to = forwardable && !TERMINAL_RESPONSES.includes(values.response) ? values.forward_to_user : null;
			record_step_response(step.name, values.response, values.remarks, values.attachment, forward_to || undefined)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Record Response"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

// -- start a submission: ONE guided entry point instead of a maze of separately-conditioned
// buttons. A Submittal is a formal review/approval process by definition, so this always ends
// with at least one reviewer configured — there is deliberately no "no review" choice here.
// Reached only when this Submittal already exists but has no submission cycle yet (e.g. created
// via the raw native form) — the ordinary creation path (SubmittalsTab.vue's "+ New Submittal",
// or DocumentDetail.vue's "Submit for Review") already creates the first cycle as part of
// creating the Submittal itself, via the same shared flow, so this empty state is the rare
// leftover case, not the common one.

function open_start_submission_dialog() {
	openSubmitForReviewFlow({
		project: props.project,
		existingSubmittal: props.submittal,
		onCreated(_name, { needsReviewers }) {
			notify_changed();
			// Ad-hoc path — immediately continue into naming the reviewer(s) rather than leaving
			// the submission sitting there with nobody assigned to it yet. A template application
			// already resolves reviewers itself, so it doesn't need this follow-up.
			if (needsReviewers) open_add_reviewer_dialog();
		},
	});
}

// -- resubmit: the SAME submittal, picking straight back up with whatever it's already tracking
// — the current issued revision of the same document(s), the same reviewer roster — rather than
// re-asking the user to reconfigure a "new" submission from scratch. A new EGC Submittal
// Revision row is still created underneath (the review history genuinely must stay separable
// cycle by cycle — that's what lets a Rejected round and the Approved round after it both stay
// visible), but nothing about using this action should feel like starting something new.

async function open_resubmit_dialog() {
	const previous = current_submission.value;
	const tracked = data.value?.tracked_documents || [];

	if (!tracked.length) {
		frappe.msgprint({
			title: __("Nothing to Resubmit"),
			message: __("This submittal has no document to resubmit yet — use Start Submission instead."),
			indicator: "orange",
		});
		return;
	}
	const missing_revision = tracked.filter((d) => !d.current_revision);
	if (missing_revision.length) {
		frappe.msgprint({
			title: __("No Issued Revision Yet"),
			message: __("{0} doesn't have an issued revision yet — issue one before resubmitting.", [
				missing_revision.map((d) => d.document_number).join(", "),
			]),
			indicator: "orange",
		});
		return;
	}

	const previous_steps = previous.steps || [];
	const doc_rows = tracked
		.map(
			(d) =>
				`<li>${frappe.utils.escape_html(d.document_number)} — ${frappe.utils.escape_html(d.title)}: <strong>${__("Rev")} ${frappe.utils.escape_html(d.current_revision_label || "—")}</strong></li>`
		)
		.join("");
	const reviewer_labels = [...new Set(previous_steps.map((s) => s.reviewer_label || s.reviewer_role))];
	const reviewer_html = reviewer_labels.length
		? `<ul>${reviewer_labels.map((label) => `<li>${frappe.utils.escape_html(label)}</li>`).join("")}</ul>`
		: `<p>${__("No formal review steps on the last cycle — this resubmits directly.")}</p>`;

	const dialog = new frappe.ui.Dialog({
		title: __("Resubmit"),
		fields: [
			{
				fieldname: "summary",
				fieldtype: "HTML",
				options: `<div>
					<div style="margin-bottom: 12px;"><strong>${__("Documents")}</strong>${doc_rows ? `<ul style="margin: 4px 0 0; padding-left: 18px;">${doc_rows}</ul>` : ""}</div>
					<div><strong>${__("Reviewers")}</strong><div style="margin-top: 4px;">${reviewer_html}</div></div>
				</div>`,
			},
		],
		primary_action_label: __("Resubmit"),
		async primary_action() {
			dialog.disable_primary_action();
			let submission_name = null;
			try {
				submission_name = await create_next_revision(props.submittal);

				for (const doc of tracked) {
					await add_submission_document(submission_name, doc.current_revision);
				}
				for (const step of previous_steps) {
					await add_review_step(submission_name, step.sequence, step.reviewer_role, step.reviewer_user, Boolean(step.is_required));
				}
				await submit_submission(submission_name);

				dialog.hide();
				notify_changed();
			} catch (e) {
				if (submission_name) {
					dialog.hide();
					notify_changed();
					frappe.msgprint({
						title: __("Resubmission Started, But Incomplete"),
						message: __("{0} was created, but this step failed: {1} Finish configuring it below.", [
							frappe.utils.escape_html(submission_name),
							e.message,
						]),
						indicator: "orange",
					});
				} else {
					dialog.enable_primary_action();
					frappe.msgprint({ title: __("Could Not Resubmit"), message: e.message, indicator: "red" });
				}
			}
		},
	});
	dialog.show();
}

// -- edit the current cycle's review dates after the fact (not just at Start Submission time) --

function open_edit_dates_dialog() {
	const s = current_submission.value;
	const dialog = new frappe.ui.Dialog({
		title: __("Edit Review Dates"),
		fields: [
			{ fieldname: "due_date", fieldtype: "Date", label: __("Response Due"), default: s.due_date },
			{
				fieldname: "required_submission_date",
				fieldtype: "Date",
				label: __("Required Submission Date"),
				default: s.required_submission_date,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "required_approval_date",
				fieldtype: "Date",
				label: __("Required Approval Date"),
				default: s.required_approval_date,
			},
			{
				fieldname: "required_on_site_date",
				fieldtype: "Date",
				label: __("Required On-Site Date"),
				default: s.required_on_site_date,
			},
			{ fieldname: "lead_time_days", fieldtype: "Int", label: __("Lead Time (Days)"), default: s.lead_time_days },
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			update_submission_dates(s.name, values)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Save"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

// -- apply workflow template ------------------------------------------------------------------

async function open_apply_template_dialog() {
	let templates = [];
	try {
		templates = await get_workflow_templates();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Load Templates"), message: e.message, indicator: "red" });
		return;
	}
	if (!templates.length) {
		frappe.msgprint(__("No workflow templates exist yet. Create one from the Submittals tab's \"Workflow Templates\" button."));
		return;
	}

	function preview_template(name) {
		const $wrapper = dialog.fields_dict.stages_preview.$wrapper;
		if (!name) {
			$wrapper.html("");
			return;
		}
		get_workflow_template_detail(name).then((detail) => {
			$wrapper.html(renderStagesPreviewHtml(detail.steps));
		});
	}

	const dialog = new frappe.ui.Dialog({
		title: __("Apply Workflow Template"),
		fields: [
			{
				fieldname: "template",
				fieldtype: "Select",
				label: __("Template"),
				options: templates.map((t) => t.name),
				reqd: 1,
				onchange: () => preview_template(dialog.get_value("template")),
			},
			{ fieldtype: "Section Break", label: __("Stages") },
			{ fieldname: "stages_preview", fieldtype: "HTML" },
		],
		primary_action_label: __("Apply"),
		primary_action(values) {
			apply_workflow_template(current_submission.value.name, values.template)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Apply Template"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
	// onchange never fires for a field's own default value — prime the preview once, immediately,
	// same fix already applied to the numbering suggestion fields elsewhere in this app.
	preview_template(dialog.get_value("template"));
}

// -- add/remove reviewers (ball in court can hold more than one person at a stage) --------------
//
// `add_review_step` is a per-reviewer call, not a bulk one — adding N people to the same stage
// means calling it N times with the same `sequence`. That's exactly how a review stage becomes
// "parallel" (submittal_control.py's `_refresh_ball_in_court` already aggregates every step of
// the CURRENT sequence into one Ball in Court label); this dialog is just what makes doing that
// from the Hub possible at all — the API already supported it, nothing in the UI called it.

function open_add_reviewer_dialog() {
	const existing_sequences = [...new Set((current_submission.value?.steps || []).map((s) => s.sequence))];
	const next_sequence = existing_sequences.length ? Math.max(...existing_sequences) : 1;

	const dialog = new frappe.ui.Dialog({
		title: __("Add Reviewer"),
		fields: [
			{
				fieldname: "sequence",
				fieldtype: "Int",
				label: __("Stage"),
				default: next_sequence,
				reqd: 1,
				description: __(
					"Reviewers sharing the same stage number review in parallel — all of them show up in Ball in Court at once. Use the next stage number to review after the current stage responds instead."
				),
			},
			{
				fieldname: "reviewer_role",
				fieldtype: "Link",
				label: __("Reviewer Role"),
				options: "EGC Stakeholder Role",
				description: __("Resolves to that role's stakeholder on this project. Leave blank if picking a user directly."),
			},
			{
				fieldname: "reviewer_user",
				fieldtype: "Link",
				label: __("Reviewer User"),
				options: "User",
				description: __("Set this instead of (or in addition to) a role to name a specific person."),
			},
			{ fieldname: "is_required", fieldtype: "Check", label: __("Required"), default: 1 },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			add_review_step(current_submission.value.name, values.sequence, values.reviewer_role, values.reviewer_user, Boolean(values.is_required))
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Reviewer"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_remove_reviewer(step) {
	frappe.confirm(__("Remove this reviewer from the submission?"), () => {
		remove_review_step(step.name)
			.then(notify_changed)
			.catch((e) => {
				frappe.msgprint({ title: __("Could Not Remove Reviewer"), message: e.message, indicator: "red" });
			});
	});
}

// -- People: multiple assignees beyond the single primary responsible_organization/
// responsible_party pair (Level 1 §31) — same generic assignments.py engine ActivityDetail.vue
// already uses, just pointed at "EGC Submittal" instead of "EGC Activity".

const ASSIGNMENT_ROLES = ["Responsible", "Assignee", "Supervisor", "Consultant", "Reviewer", "Contractor", "Watcher"];

function open_add_assignment_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Person"),
		fields: [
			{
				fieldname: "person",
				fieldtype: "Link",
				label: __("Person"),
				options: "User",
				description: __("Leave blank to assign a whole Organization with no specific individual named."),
				onchange: async function () {
					const person = this.value;
					if (!person) return;
					const info = await get_person_info(person).catch(() => null);
					if (info && info.organization) dialog.set_value("organization", info.organization);
				},
			},
			{
				fieldname: "organization",
				fieldtype: "Link",
				label: __("Organization"),
				options: "Customer",
				description: __("Defaults from the Person's own organization when one is picked above."),
			},
			{
				fieldname: "assignment_role",
				fieldtype: "Select",
				label: __("Role on this Submittal"),
				options: ASSIGNMENT_ROLES,
				default: "Responsible",
				reqd: 1,
			},
			{ fieldname: "is_primary", fieldtype: "Check", label: __("Primary") },
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			add_assignment(
				"EGC Submittal",
				props.submittal,
				values.assignment_role,
				values.person,
				values.organization,
				values.remarks,
				Boolean(values.is_primary)
			)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Person"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_remove_assignment(row) {
	frappe.confirm(__("Remove {0} from this Submittal?", [row.person_name || row.organization_name]), () => {
		remove_assignment(row.name)
			.then(notify_changed)
			.catch((e) => {
				frappe.msgprint({ title: __("Could Not Remove"), message: e.message, indicator: "red" });
			});
	});
}

// -- documents on the current (Draft) submission -----------------------------------------------

function open_add_document_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Document Revision"),
		fields: [
			{
				fieldname: "document_revision",
				fieldtype: "Link",
				label: __("Document Revision"),
				options: "EGC Project Document Revision",
				reqd: 1,
				get_query: () => ({
					filters: { project: props.project, docstatus: 1, revision_status: "Issued" },
				}),
			},
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			add_submission_document(current_submission.value.name, values.document_revision)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Document"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_remove_document(row) {
	frappe.confirm(__("Remove this document from the submission?"), () => {
		remove_submission_document(current_submission.value.name, row.name)
			.then(notify_changed)
			.catch((e) => {
				frappe.msgprint({ title: __("Could Not Remove Document"), message: e.message, indicator: "red" });
			});
	});
}

// -- comments (generic thread, reachable by external reviewers too — comments.py's only gate is
// read access to the Submittal itself, same as everything else on this page). Rendered as part
// of the unified timeline below, not a separate box — see `timeline_events`. -------------------

const comments = ref([]);
const new_comment = ref("");
const posting_comment = ref(false);

async function load_comments() {
	try {
		comments.value = await get_comments("EGC Submittal", props.submittal);
	} catch (e) {
		comments.value = [];
	}
}
watch(() => props.submittal, load_comments, { immediate: true });

async function do_post_comment() {
	if (!new_comment.value.trim()) return;
	posting_comment.value = true;
	try {
		await add_comment("EGC Submittal", props.submittal, new_comment.value);
		new_comment.value = "";
		await load_comments();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Post Comment"), message: e.message, indicator: "red" });
	} finally {
		posting_comment.value = false;
	}
}

function open_link_activity_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Link Activity"),
		fields: [
			{
				fieldname: "activity",
				fieldtype: "Link",
				label: __("Activity"),
				options: "EGC Activity",
				reqd: 1,
				description: __("Only leaf Activities are shown — a Submittal belongs on the Activity that represents the actual work, not a Group Activity."),
				get_query: () => ({ filters: { project: props.project, is_group: 0 } }),
			},
		],
		primary_action_label: __("Link"),
		primary_action(values) {
			link_activity_record(values.activity, "EGC Submittal", props.submittal, "Reference")
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Link Activity"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

// -- unified timeline: every cycle's start/submit/response, plus comments, merged into ONE
// chronological feed sorted by real timestamp — this is what replaced the old "Review Cycle"
// box (current cycle only, vague icons) and the separate "Earlier Review Cycles" list (one line
// per cycle, no reasons visible). Everything that happened is here, in the order it happened,
// same shape as a GitHub pull request's conversation thread. ------------------------------------

function event_response(event) {
	return event.type === "step_responded" ? event.step.response : event.submission.response;
}

function event_tone(event) {
	if (event.type === "submitted" || event.type === "step_assigned") return "blue";
	if (event.type === "step_responded" || event.type === "responded") return response_tone(event_response(event));
	return "grey";
}

function event_icon(event) {
	if (event.type === "started") return "+";
	if (event.type === "submitted") return "↑";
	if (event.type === "step_assigned") return "→";
	if (event.type === "comment") return "●";
	const response = event_response(event);
	if (RESPONSE_IS_FINAL_OK.includes(response)) return "✓";
	if (response === "Rejected") return "✕";
	if (response === "Revise & Resubmit") return "↺";
	return "○";
}

// `date_submitted`/`response_date` are Date fields (day-only, see the doctype JSON) — sorting the
// whole feed by those directly interleaves them wrongly against same-day Datetime fields like
// `creation` (a response recorded at 18:00 the day it was requested would sort BEFORE the 09:00
// "started" event, since midnight < 18:00). Sidestepping that: events within one cycle are built
// in a structurally guaranteed order (started, then submitted, then each response as it actually
// came in — ranked by the step's own `modified`, a real Datetime — then the no-steps response),
// and only comments (which DO have a real Datetime `creation`) are interleaved across that
// sequence, matched against the real Datetimes the other events do have (`creation`/`modified`).
const timeline_events = computed(() => {
	const submissions = [...(data.value?.submissions || [])].reverse(); // oldest cycle first

	const groups = submissions.map((s) => {
		const events = [];
		events.push({ type: "started", key: `${s.name}-started`, timestamp: s.creation, submission: s });
		if (s.docstatus === 1) {
			events.push({ type: "submitted", key: `${s.name}-submitted`, timestamp: s.creation, submission: s });
		}
		const responded_steps = (s.steps || [])
			.filter((step) => step.status === "Responded")
			.sort((a, b) => new Date(a.modified) - new Date(b.modified));
		for (const step of responded_steps) {
			events.push({ type: "step_responded", key: step.name, timestamp: step.modified, submission: s, step });
		}
		// Only forwarded steps get their own "assigned" event — a pre-planned step's `creation`
		// predates the submission itself (add_review_step/apply_workflow_template only ever run
		// pre-submit), so it would show as "assigned" before "submitted", which is backwards. A
		// forwarded step's `creation` IS the real moment it was handed off — exactly the live
		// routing hop this timeline should make visible.
		const forwarded_steps = (s.steps || []).filter((step) => step.origin === "Forwarded");
		for (const step of forwarded_steps) {
			events.push({ type: "step_assigned", key: `${step.name}-assigned`, timestamp: step.creation, submission: s, step });
		}
		if (!(s.steps || []).length && s.submission_status === "Responded") {
			events.push({
				type: "responded",
				key: `${s.name}-responded`,
				timestamp: s.modified || s.response_date,
				submission: s,
			});
		}
		return { anchor: s.creation, events };
	});

	for (const c of comments.value) {
		const comment_time = new Date(c.creation).getTime();
		let bucket = groups[0];
		for (const g of groups) {
			if (new Date(g.anchor).getTime() <= comment_time) bucket = g;
		}
		if (!bucket) continue;
		let insert_at = bucket.events.length;
		for (let i = 0; i < bucket.events.length; i++) {
			if (new Date(bucket.events[i].timestamp).getTime() > comment_time) {
				insert_at = i;
				break;
			}
		}
		bucket.events.splice(insert_at, 0, { type: "comment", key: `comment-${c.name}`, timestamp: c.creation, comment: c });
	}

	return groups.flatMap((g) => g.events);
});
</script>

<template>
	<div class="submittal-page">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />

		<template v-else-if="data">
			<div class="submittal-page__topbar">
				<a href="#" class="hub-link submittal-page__back" @click.prevent="$emit('close')">
					{{ __("← Back to Submittals") }}
				</a>
				<div class="submittal-page__topbar-actions">
					<a href="#" class="hub-link hub-link--muted" @click.prevent="open_form">
						{{ __("View raw record ↗") }}
					</a>
					<a
						v-if="canWrite && !has_submitted_history"
						href="#"
						class="hub-link hub-link--danger"
						@click.prevent="confirm_delete_submittal"
					>
						{{ __("Delete") }}
					</a>
					<span v-else-if="canWrite" class="submittal-permanent-note" :title="__('This submittal has submitted review history, which is permanent and cannot be deleted.')">
						{{ __("History is permanent") }}
					</span>
				</div>
			</div>

			<div class="submittal-page__identity">
				<div class="submittal-page__code">{{ data.submittal.submittal_number }}</div>
				<h1 class="submittal-page__title">{{ data.submittal.title }}</h1>
				<div class="submittal-page__status-row">
					<StatusPill :status="data.submittal.submittal_status" />
					<span v-if="data.submittal.ball_in_court" class="indicator-pill blue">
						{{ __("Ball in Court") }}: {{ data.submittal.ball_in_court }}
					</span>
					<span class="submittal-page__meta-inline">
						{{ data.submittal.submittal_type || "—" }}<template v-if="data.submittal.discipline"> · {{ data.submittal.discipline }}</template>
					</span>
				</div>
			</div>

			<section v-if="!current_submission" class="submittal-page__empty-cycle">
				<EmptyState
					:title="__('No submission cycle yet')"
					:description="__('A Submittal is a formal review — start the first submission to attach the document revision(s) needing approval and name who reviews them.')"
					:action-label="canWrite ? __('Start Submission') : ''"
					@action="open_start_submission_dialog"
				/>
			</section>

			<template v-else>
				<div class="submittal-banner" :class="`submittal-banner--${banner_tone}`">
					<div class="submittal-banner__main">
						<p class="submittal-banner__text">{{ next_step_text }}</p>
						<div v-if="rejection_reason_text" class="submittal-banner__reason">
							<span class="submittal-banner__reason-label">{{ current_submission.response }}:</span>
							{{ rejection_reason_text }}
						</div>
					</div>
					<div v-if="canWrite" class="submittal-banner__actions">
						<button
							v-if="current_submission.docstatus === 0"
							type="button"
							class="btn btn-sm btn-primary"
							:disabled="submitting || !current_submission.documents.length"
							@click="do_submit"
						>
							{{ __("Submit") }}
						</button>
						<button
							v-if="current_submission.submission_status === 'Responded' && !RESPONSE_IS_FINAL_OK.includes(current_submission.response)"
							type="button"
							class="btn btn-sm btn-primary"
							@click="open_resubmit_dialog"
						>
							{{ __("Resubmit") }}
						</button>
					</div>
				</div>

				<div class="submittal-page__body">
					<div class="submittal-main">
						<div class="submittal-timeline">
							<div v-for="event in timeline_events" :key="event.key" class="submittal-timeline__row">
								<div class="submittal-timeline__rail">
									<span class="submittal-timeline__dot" :class="`submittal-timeline__dot--${event_tone(event)}`">
										{{ event_icon(event) }}
									</span>
									<span class="submittal-timeline__line" />
								</div>

								<div class="submittal-timeline__content">
									<template v-if="event.type === 'started'">
										<p class="submittal-timeline__headline">
											<strong>{{ event.submission.revision_label }}</strong> {{ __("started") }}
											<span v-if="event.submission.owner" class="submittal-timeline__by">— {{ event.submission.owner }}</span>
											<span class="submittal-timeline__when">{{ format_datetime(event.timestamp) }}</span>
										</p>
										<ul v-if="(event.submission.documents || []).length" class="submittal-timeline__docs">
											<li v-for="row in event.submission.documents" :key="row.document_revision">
												{{ row.document_title || row.document }} ({{ __("Rev") }} {{ row.revision }})
											</li>
										</ul>
									</template>

									<template v-else-if="event.type === 'submitted'">
										<p class="submittal-timeline__headline">
											{{ __("Submitted for review") }}
											<span v-if="event.submission.submitted_by" class="submittal-timeline__by">— {{ event.submission.submitted_by }}</span>
											<span class="submittal-timeline__when">{{ format_datetime(event.timestamp) }}</span>
										</p>
									</template>

									<template v-else-if="event.type === 'step_responded'">
										<p class="submittal-timeline__headline">
											<strong>{{ event.step.reviewer_label || event.step.reviewer_role }}</strong>
											{{ __("responded") }}
											<span class="indicator-pill" :class="event_tone(event)">{{ event.step.response }}</span>
											<span class="submittal-timeline__when">{{ format_datetime(event.timestamp) }}</span>
										</p>
										<p v-if="event.step.response_remarks" class="submittal-timeline__remarks">{{ event.step.response_remarks }}</p>
										<a
											v-if="event.step.response_attachment"
											:href="event.step.response_attachment"
											target="_blank"
											rel="noopener"
											class="hub-link submittal-timeline__attachment"
										>
											{{ __("View attachment") }}
										</a>
									</template>

									<template v-else-if="event.type === 'step_assigned'">
										<p class="submittal-timeline__headline">
											{{ __("Forwarded to") }}
											<strong>{{ event.step.reviewer_label || event.step.reviewer_role }}</strong>
											<span class="submittal-timeline__when">{{ format_datetime(event.timestamp) }}</span>
										</p>
									</template>

									<template v-else-if="event.type === 'responded'">
										<p class="submittal-timeline__headline">
											{{ __("Response recorded") }}
											<span class="indicator-pill" :class="event_tone(event)">{{ event.submission.response }}</span>
											<span v-if="event.submission.responded_by" class="submittal-timeline__by">— {{ event.submission.responded_by }}</span>
											<span class="submittal-timeline__when">{{ format_datetime(event.timestamp) }}</span>
										</p>
										<p v-if="event.submission.response_remarks" class="submittal-timeline__remarks">{{ event.submission.response_remarks }}</p>
									</template>

									<template v-else-if="event.type === 'comment'">
										<p class="submittal-timeline__headline">
											<strong>{{ event.comment.owner }}</strong> {{ __("commented") }}
											<span class="submittal-timeline__when">{{ format_datetime(event.timestamp) }}</span>
										</p>
										<p class="submittal-timeline__remarks submittal-timeline__remarks--comment">{{ event.comment.content }}</p>
									</template>
								</div>
							</div>
						</div>

						<div class="submittal-composer">
							<textarea
								v-model="new_comment"
								class="form-control"
								rows="2"
								:placeholder="__('Add a comment…')"
							></textarea>
							<button
								type="button"
								class="btn btn-sm btn-primary"
								:disabled="posting_comment || !new_comment.trim()"
								@click="do_post_comment"
							>
								{{ __("Post") }}
							</button>
						</div>
					</div>

					<div class="submittal-sidebar">
						<div class="submittal-sidebar__card">
							<div class="activity-detail__head-row">
								<div class="activity-detail__section-title">{{ __("Documents") }}</div>
								<button
									v-if="canWrite && current_submission.docstatus === 0"
									type="button"
									class="btn btn-xs btn-default"
									@click="open_add_document_dialog"
								>
									{{ __("Add") }}
								</button>
							</div>
							<div v-if="tracked_documents_display.length" class="submittal-tracked-docs">
								<div v-for="doc in tracked_documents_display" :key="doc.name" class="submittal-tracked-docs__item">
									<a href="#" class="hub-link" @click.prevent="open_document(doc.name)">
										{{ doc.document_number }} — {{ doc.title }}
									</a>
									<span class="submittal-tracked-docs__rev">
										{{ __("Latest issued") }}: {{ doc.current_revision_label || "—" }}
									</span>
									<span v-if="!doc.is_current_in_this_cycle && doc.current_revision" class="indicator-pill orange">
										{{ __("Newer revision available") }}
									</span>
								</div>
							</div>
							<EmptyState v-else :title="__('No documents attached yet')" />
							<ul v-if="canWrite && current_submission.docstatus === 0 && current_submission.documents.length" class="activity-detail__list submittal-sidebar__sublist">
								<li v-for="row in current_submission.documents" :key="row.name">
									<span class="submittal-sidebar__sublist-label">{{ row.document_title || row.document }} (Rev {{ row.revision }})</span>
									<button type="button" class="btn btn-xs btn-default" @click="confirm_remove_document(row)">
										{{ __("Remove") }}
									</button>
								</li>
							</ul>
						</div>

						<div class="submittal-sidebar__card">
							<div class="activity-detail__head-row">
								<div class="activity-detail__section-title">{{ __("Reviewers") }}</div>
								<button
									v-if="canWrite && current_submission.docstatus === 0"
									type="button"
									class="btn btn-xs btn-default"
									@click="open_add_reviewer_dialog"
								>
									{{ __("Add") }}
								</button>
							</div>
							<!-- At-a-glance chain (Aconex-inspired "Workflow Steps" panel — a connected
							     step visualization, not just a flat list) above the detailed,
							     interactive stage list below it. Same data, two views: this one for
							     "what's the shape of this review," the list below for actually acting
							     on it. -->
							<WorkflowStepper v-if="has_steps" :stages="stages" compact />
							<template v-if="has_steps">
								<div v-for="stage in stages" :key="stage.sequence" class="submittal-sidebar__stage">
									<div class="submittal-sidebar__stage-label">{{ __("Stage {0}", [stage.sequence]) }}</div>
									<div v-for="step in stage.steps" :key="step.name" class="submittal-sidebar__reviewer">
										<span class="submittal-sidebar__reviewer-name">
											{{ step.reviewer_role }}<template v-if="step.reviewer_label">: {{ step.reviewer_label }}</template>
											<span v-if="next_reviewer_hint(step)" class="submittal-sidebar__next-hint">
												{{ __("→ next: {0}", [next_reviewer_hint(step)]) }}
											</span>
										</span>
										<StatusPill :status="step.status" />
										<button
											v-if="can_respond_to(step)"
											type="button"
											class="btn btn-xs btn-primary"
											@click="open_record_response_dialog(step)"
										>
											{{ __("Respond") }}
										</button>
										<button
											v-if="canWrite && current_submission.docstatus === 0"
											type="button"
											class="btn btn-xs btn-default"
											:title="__('Remove reviewer')"
											@click="confirm_remove_reviewer(step)"
										>
											&times;
										</button>
									</div>
								</div>
							</template>
							<div v-else-if="canWrite && current_submission.docstatus === 0" class="submittal-workflow-empty">
								<button type="button" class="btn btn-xs btn-default" @click="open_apply_template_dialog">
									{{ __("Apply Template") }}
								</button>
							</div>
							<EmptyState v-else :title="__('No formal review steps')" />
						</div>

						<div class="submittal-sidebar__card">
							<div class="activity-detail__section-title">{{ __("Details") }}</div>
							<dl class="activity-detail__meta submittal-sidebar__meta">
								<div>
									<dt>{{ __("Responsible Party") }}</dt>
									<dd>{{ data.submittal.responsible_party || "—" }}</dd>
								</div>
								<div>
									<dt>{{ __("Submittal Manager") }}</dt>
									<dd>{{ data.submittal.submittal_manager || "—" }}</dd>
								</div>
								<div>
									<dt>{{ __("Due Date") }}</dt>
									<dd>{{ format_date(data.submittal.current_due_date) }}</dd>
								</div>
							</dl>
							<div class="activity-detail__head-row" style="margin-top: 14px">
								<div class="activity-detail__dep-label">{{ __("Review Dates") }}</div>
								<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_edit_dates_dialog">
									{{ __("Edit") }}
								</button>
							</div>
							<dl class="activity-detail__meta submittal-sidebar__meta">
								<div>
									<dt>{{ __("Response Due") }}</dt>
									<dd>{{ format_date(current_submission.due_date) }}</dd>
								</div>
								<div>
									<dt>{{ __("Required Submission") }}</dt>
									<dd>{{ format_date(current_submission.required_submission_date) }}</dd>
								</div>
								<div>
									<dt>{{ __("Required Approval") }}</dt>
									<dd>{{ format_date(current_submission.required_approval_date) }}</dd>
								</div>
								<div>
									<dt>{{ __("Required On-Site") }}</dt>
									<dd>{{ format_date(current_submission.required_on_site_date) }}</dd>
								</div>
								<div>
									<dt>{{ __("Lead Time") }}</dt>
									<dd>{{ current_submission.lead_time_days ? __("{0}d", [current_submission.lead_time_days]) : "—" }}</dd>
								</div>
							</dl>
						</div>

						<div class="submittal-sidebar__card">
							<div class="activity-detail__head-row">
								<div class="activity-detail__section-title">{{ __("Team") }}</div>
								<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_add_assignment_dialog">
									{{ __("Add") }}
								</button>
							</div>
							<p class="submittal-section-hint">
								{{ __("Visibility and notifications only — not the reviewers above, who must actually respond.") }}
							</p>
							<EmptyState v-if="!(data.assignments || []).length" :title="__('No one assigned yet')" />
							<ul v-else class="activity-detail__list">
								<li v-for="row in data.assignments" :key="row.name">
									<div>
										<span class="activity-detail__link">{{ row.person_name || row.organization_name || __("Unnamed") }}</span>
										<span v-if="row.is_primary" class="indicator-pill blue">{{ __("Primary") }}</span>
									</div>
									<div class="activity-links__meta">
										<span class="activity-detail__dep-type">{{ row.assignment_role }}</span>
										<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="confirm_remove_assignment(row)">
											{{ __("Remove") }}
										</button>
									</div>
								</li>
							</ul>
						</div>

						<div class="submittal-sidebar__card">
							<div class="activity-detail__head-row">
								<div class="activity-detail__section-title">{{ __("Related Activities") }}</div>
								<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_link_activity_dialog">
									{{ __("Link") }}
								</button>
							</div>
							<EmptyState v-if="!(data.related_activities || []).length" :title="__('No linked activities yet')" />
							<ul v-else class="activity-detail__list">
								<li v-for="row in data.related_activities" :key="row.name">
									<a href="#" class="activity-detail__link" @click.prevent="open_activity(row.activity)">
										{{ row.activity_code }}: {{ row.activity_name }}
									</a>
									<StatusPill :status="row.status" />
								</li>
							</ul>
						</div>
					</div>
				</div>
			</template>
		</template>
	</div>
</template>

<style scoped>
.submittal-page {
	display: flex;
	flex-direction: column;
	gap: 18px;
}

.submittal-page__topbar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
}

.submittal-page__back {
	font-weight: 500;
}

.submittal-page__topbar-actions {
	display: flex;
	align-items: center;
	gap: 14px;
}

.hub-link--muted {
	color: var(--text-muted);
	font-size: var(--text-xs);
}

.hub-link--danger {
	color: var(--red-500, #d1483e);
}

.submittal-permanent-note {
	font-size: var(--text-xs);
	color: var(--text-muted);
	cursor: help;
}

.submittal-page__identity {
	border-bottom: 1px solid var(--border-color);
	padding-bottom: 16px;
}

.submittal-page__code {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-muted);
}

.submittal-page__title {
	font-size: var(--text-2xl, 22px);
	font-weight: 600;
	color: var(--text-color);
	margin: 2px 0 10px;
}

.submittal-page__status-row {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 8px 12px;
}

.submittal-page__meta-inline {
	font-size: var(--text-sm);
	color: var(--text-muted);
}

.submittal-page__empty-cycle {
	padding: 24px 0;
}

.submittal-banner {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	flex-wrap: wrap;
	gap: 10px 16px;
	border: 1px solid var(--border-color);
	border-left: 4px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 14px 16px;
	background: var(--subtle-fg, var(--control-bg));
}

.submittal-banner--green {
	border-left-color: var(--green-500, #2e7d32);
}

.submittal-banner--red {
	border-left-color: var(--red-500, #d1483e);
}

.submittal-banner--orange {
	border-left-color: var(--orange-500, #d98c26);
}

.submittal-banner--blue {
	border-left-color: var(--blue-500, #2f6fed);
}

.submittal-banner__main {
	flex: 1 1 320px;
}

.submittal-banner__text {
	margin: 0;
	font-size: var(--text-sm);
	color: var(--text-color);
}

.submittal-banner__reason {
	margin-top: 8px;
	font-size: var(--text-sm);
	color: var(--text-color);
}

.submittal-banner__reason-label {
	font-weight: 600;
	margin-right: 4px;
}

.submittal-banner__actions {
	display: flex;
	gap: 8px;
	flex: 0 0 auto;
}

.submittal-page__body {
	display: grid;
	grid-template-columns: minmax(0, 1fr) 300px;
	gap: 28px;
	align-items: start;
}

@media (max-width: 900px) {
	.submittal-page__body {
		grid-template-columns: 1fr;
	}
}

.submittal-main {
	min-width: 0;
}

.submittal-timeline {
	display: flex;
	flex-direction: column;
}

.submittal-timeline__row {
	display: flex;
	gap: 12px;
}

.submittal-timeline__rail {
	display: flex;
	flex-direction: column;
	align-items: center;
	flex: 0 0 auto;
}

.submittal-timeline__dot {
	width: 24px;
	height: 24px;
	flex: 0 0 auto;
	border-radius: 50%;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 12px;
	font-weight: 700;
	background: var(--control-bg);
	color: var(--text-muted);
	border: 1px solid var(--border-color);
}

.submittal-timeline__dot--green {
	color: var(--green-500, #2e7d32);
	border-color: var(--green-200, var(--green-500, #2e7d32));
}

.submittal-timeline__dot--red {
	color: var(--red-500, #d1483e);
	border-color: var(--red-200, var(--red-500, #d1483e));
}

.submittal-timeline__dot--orange {
	color: var(--orange-500, #d98c26);
	border-color: var(--orange-200, var(--orange-500, #d98c26));
}

.submittal-timeline__dot--blue {
	color: var(--blue-500, #2f6fed);
	border-color: var(--blue-200, var(--blue-500, #2f6fed));
}

.submittal-timeline__line {
	flex: 1 1 auto;
	width: 1px;
	background: var(--border-color);
	min-height: 12px;
}

.submittal-timeline__row:last-child .submittal-timeline__line {
	display: none;
}

.submittal-timeline__content {
	flex: 1 1 auto;
	min-width: 0;
	padding-bottom: 20px;
}

.submittal-timeline__headline {
	margin: 3px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 6px;
}

.submittal-timeline__by {
	color: var(--text-muted);
	font-weight: 400;
}

.submittal-timeline__when {
	color: var(--text-muted);
	font-size: var(--text-xs);
	margin-left: auto;
}

.submittal-timeline__docs {
	list-style: none;
	margin: 6px 0 0;
	padding: 0;
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.submittal-timeline__remarks {
	margin: 6px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: pre-wrap;
	background: var(--subtle-fg, var(--control-bg));
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 8px 10px;
}

.submittal-timeline__remarks--comment {
	background: var(--fg-color);
}

.submittal-timeline__attachment {
	display: inline-block;
	margin-top: 6px;
	font-size: var(--text-xs);
}

.submittal-composer {
	display: flex;
	flex-direction: column;
	gap: 8px;
	align-items: flex-end;
	margin-left: 36px;
}

.submittal-composer textarea {
	width: 100%;
	resize: vertical;
}

.submittal-sidebar {
	display: flex;
	flex-direction: column;
	gap: 16px;
}

.submittal-sidebar__card {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	background: var(--fg-color);
	padding: 16px;
}

.submittal-sidebar__sublist {
	margin-top: 10px;
}

.submittal-sidebar__sublist-label {
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.submittal-sidebar__stage {
	display: flex;
	flex-direction: column;
	gap: 4px;
	margin-bottom: 10px;
}

.submittal-sidebar__stage:last-child {
	margin-bottom: 0;
}

.submittal-sidebar__stage-label {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
}

.submittal-sidebar__reviewer {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 6px;
	font-size: var(--text-sm);
}

.submittal-sidebar__reviewer-name {
	flex: 1 1 auto;
	color: var(--text-color);
	overflow-wrap: break-word;
	word-break: break-word;
}

.submittal-sidebar__next-hint {
	display: block;
	color: var(--text-muted);
	font-size: var(--text-xs);
}

.submittal-sidebar__meta {
	grid-template-columns: 1fr;
	gap: 8px 0;
}

.submittal-workflow-empty {
	display: flex;
	gap: 8px;
}

.activity-detail__section-title {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
	padding-bottom: 8px;
	margin-bottom: 12px;
	border-bottom: 1px solid var(--border-color);
}

.activity-detail__head-row {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 8px;
	padding-bottom: 8px;
	margin-bottom: 12px;
	border-bottom: 1px solid var(--border-color);
}

.activity-detail__head-row .activity-detail__section-title {
	padding-bottom: 0;
	margin-bottom: 0;
	border-bottom: none;
}

.activity-detail__meta {
	display: grid;
	gap: 10px 16px;
	margin: 0;
}

.activity-detail__meta dt {
	font-size: var(--text-xs);
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
}

.activity-detail__meta dd {
	margin: 2px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
	overflow-wrap: break-word;
	word-break: break-word;
}

.activity-detail__dep-label {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
	margin-bottom: 6px;
}

.activity-detail__list {
	list-style: none;
	margin: 0;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.activity-detail__list li {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 10px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 8px 12px;
}

.activity-detail__link {
	color: var(--text-color);
	font-weight: 500;
}

.activity-detail__dep-type {
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.activity-links__meta {
	display: flex;
	align-items: center;
	gap: 8px;
	flex: 0 0 auto;
}

.submittal-section-hint {
	font-size: var(--text-xs);
	color: var(--text-muted);
	margin: -4px 0 10px;
}

.submittal-tracked-docs {
	display: flex;
	flex-direction: column;
	gap: 6px;
}

.submittal-tracked-docs__item {
	display: flex;
	flex-direction: column;
	gap: 2px;
	font-size: var(--text-sm);
	overflow-wrap: break-word;
	word-break: break-word;
}

.submittal-tracked-docs__rev {
	color: var(--text-muted);
	font-size: var(--text-xs);
}
</style>
