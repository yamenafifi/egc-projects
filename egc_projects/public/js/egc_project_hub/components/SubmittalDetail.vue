<!-- Submittal detail workspace (docs/ARCHITECTURE_V2.md §7, §16 of the original brief). Same
     right-hand drawer shell as DocumentDetail.vue/ActivityDetail.vue.

     Shows EVERY submission cycle, not just the current one — "confirm full history remains
     visible" is one of the build brief's own acceptance checks, and a Revise & Resubmit cycle
     is exactly the case where hiding history would be actively misleading. -->
<script setup>
import { computed, ref, watch } from "vue";
import {
	get_submittal_detail,
	submit_submission,
	mark_under_review,
	record_response,
	create_next_revision,
	create_first_submission,
	apply_workflow_template,
	get_workflow_templates,
	record_step_response,
	add_submission_document,
	remove_submission_document,
	add_review_step,
	remove_review_step,
} from "./submittals_api";
import { link_activity_record, unlink_activity_record } from "./activities_api";
import { get_comments, add_comment } from "./comments_api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";

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

function open_activity(name) {
	frappe.set_route("Form", "EGC Activity", name);
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

// The current cycle is always the FIRST row — submissions are returned newest-first
// (submission_seq desc), matching the register's own "current" convention.
const current_submission = computed(() => (data.value?.submissions || [])[0] || null);
const history_submissions = computed(() => (data.value?.submissions || []).slice(1));

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

function stage_icon(step) {
	if (step.status === "Responded") return "✓";
	if (step.status === "In Review") return "●";
	if (step.status === "Skipped") return "⊘";
	return "○";
}

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

// -- submit / mark under review / record response (no-steps v1 path) -------------------------

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

async function do_mark_under_review() {
	try {
		await mark_under_review(current_submission.value.name);
		notify_changed();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Update"), message: e.message, indicator: "red" });
	}
}

const RESPONSES = ["Approved", "Approved with Comments", "Revise & Resubmit", "Rejected"];

function open_record_response_dialog(step) {
	const is_step = Boolean(step);
	const fields = [
		{ fieldname: "response", fieldtype: "Select", label: __("Response"), options: RESPONSES, reqd: 1 },
		{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
	];
	// Only a review step already has a docname to attach the file to (the step is inserted the
	// moment a reviewer is added) — the no-steps v1 path has nothing to bind an Attach field to.
	if (is_step) {
		fields.push({
			fieldname: "attachment",
			fieldtype: "Attach",
			label: __("Attachment"),
			description: __("Optional — a marked-up file you're returning with your response (e.g. an annotated drawing)."),
			options: { doctype: "EGC Submittal Review Step", docname: step.name, fieldname: "response_attachment" },
		});
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Record Response"),
		fields,
		primary_action_label: __("Record"),
		primary_action(values) {
			const action = is_step
				? record_step_response(step.name, values.response, values.remarks, values.attachment)
				: record_response(current_submission.value.name, values.response, values.remarks);
			action
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

async function do_create_next_revision() {
	try {
		await create_next_revision(props.submittal);
		notify_changed();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Create Next Revision"), message: e.message, indicator: "red" });
	}
}

async function do_create_first_submission() {
	try {
		await create_first_submission(props.submittal);
		notify_changed();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Create Submission"), message: e.message, indicator: "red" });
	}
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
		frappe.msgprint(__("No workflow templates exist yet. Create one from EGC Submittal Workflow Template."));
		return;
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
			},
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

// -- related activities ------------------------------------------------------------------------

// -- comments (generic thread, reachable by external reviewers too — comments.py's only gate is
// read access to the Submittal itself, same as everything else on this drawer) -----------------

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

function format_datetime(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
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
</script>

<template>
	<div class="activity-detail__backdrop" @click.self="$emit('close')">
		<div class="activity-detail__panel" role="dialog" aria-modal="true">
			<div class="activity-detail__header">
				<div class="activity-detail__identity">
					<div class="activity-detail__code">{{ data?.submittal?.submittal_number || submittal }}</div>
					<div class="activity-detail__name">{{ data?.submittal?.title || "" }}</div>
				</div>
				<div class="activity-detail__header-actions">
					<a href="#" class="hub-link" @click.prevent="open_form">{{ __("Open Form") }}</a>
					<button type="button" class="activity-detail__close" :aria-label="__('Close')" @click="$emit('close')">
						&times;
					</button>
				</div>
			</div>

			<div class="activity-detail__body">
				<LoadingState v-if="loading" :rows="6" />
				<ErrorState v-else-if="error" :message="error" @retry="reload" />

				<template v-else-if="data">
					<section class="activity-detail__section">
						<div class="activity-detail__status-row">
							<StatusPill :status="data.submittal.submittal_status" />
							<span v-if="data.submittal.ball_in_court" class="indicator-pill blue">
								{{ __("Ball in Court") }}: {{ data.submittal.ball_in_court }}
							</span>
						</div>
						<dl class="activity-detail__meta">
							<div>
								<dt>{{ __("Type") }}</dt>
								<dd>{{ data.submittal.submittal_type || "—" }}</dd>
							</div>
							<div>
								<dt>{{ __("Discipline") }}</dt>
								<dd>{{ data.submittal.discipline || "—" }}</dd>
							</div>
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
					</section>

					<section v-if="!current_submission" class="activity-detail__section">
						<EmptyState
							:title="__('No submission cycle yet')"
							:description="__('Start the first submission to attach controlled document revisions and begin review.')"
							:action-label="canWrite ? __('Create First Submission') : ''"
							@action="do_create_first_submission"
						/>
					</section>

					<section v-if="current_submission" class="activity-detail__section">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">
								{{ __("Current Submission") }} — {{ current_submission.revision_label }}
							</div>
							<div v-if="canWrite">
								<button
									v-if="current_submission.docstatus === 0 && !has_steps"
									type="button"
									class="btn btn-xs btn-default"
									@click="open_apply_template_dialog"
								>
									{{ __("Apply Workflow Template") }}
								</button>
								<button
									v-if="current_submission.docstatus === 0"
									type="button"
									class="btn btn-xs btn-default"
									@click="open_add_reviewer_dialog"
								>
									{{ __("Add Reviewer") }}
								</button>
								<button
									v-if="current_submission.docstatus === 0"
									type="button"
									class="btn btn-xs btn-primary"
									:disabled="submitting || !current_submission.documents.length"
									@click="do_submit"
								>
									{{ __("Submit") }}
								</button>
								<button
									v-if="current_submission.docstatus === 1 && current_submission.submission_status === 'Submitted' && !has_steps"
									type="button"
									class="btn btn-xs btn-default"
									@click="do_mark_under_review"
								>
									{{ __("Mark Under Review") }}
								</button>
								<button
									v-if="current_submission.docstatus === 1 && ['Submitted', 'Under Review'].includes(current_submission.submission_status) && !has_steps"
									type="button"
									class="btn btn-xs btn-default"
									@click="open_record_response_dialog(null)"
								>
									{{ __("Record Response") }}
								</button>
								<button
									v-if="current_submission.submission_status === 'Responded'"
									type="button"
									class="btn btn-xs btn-primary"
									@click="do_create_next_revision"
								>
									{{ __("New Submission") }}
								</button>
							</div>
						</div>

						<StatusPill :status="current_submission.response || current_submission.submission_status" />

						<!-- Workflow timeline: only rendered when this cycle actually has review steps. -->
						<div v-if="has_steps" class="submittal-workflow">
							<div v-for="stage in stages" :key="stage.sequence" class="submittal-workflow__stage">
								<div
									v-for="step in stage.steps"
									:key="step.name"
									class="submittal-workflow__step"
									:class="`submittal-workflow__step--${step.status.toLowerCase().replace(' ', '-')}`"
								>
									<span class="submittal-workflow__icon">{{ stage_icon(step) }}</span>
									<span class="submittal-workflow__who">
										{{ step.reviewer_role }}<template v-if="step.reviewer_label">: {{ step.reviewer_label }}</template>
										<span v-if="!step.is_required" class="submittal-workflow__optional">({{ __("optional") }})</span>
									</span>
									<span v-if="step.response" class="submittal-workflow__response">{{ step.response }}</span>
									<a
										v-if="step.response_attachment"
										:href="step.response_attachment"
										target="_blank"
										rel="noopener"
										class="hub-link"
										:title="__('Response attachment')"
									>
										📎
									</a>
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
						</div>

						<div class="activity-detail__head-row" style="margin-top: 14px">
							<div class="activity-detail__dep-label">{{ __("Documents") }}</div>
							<button
								v-if="canWrite && current_submission.docstatus === 0"
								type="button"
								class="btn btn-xs btn-default"
								@click="open_add_document_dialog"
							>
								{{ __("Add Document") }}
							</button>
						</div>
						<EmptyState v-if="!current_submission.documents.length" :title="__('No documents attached yet')" />
						<ul v-else class="activity-detail__list">
							<li v-for="row in current_submission.documents" :key="row.name">
								<a href="#" class="activity-detail__link" @click.prevent="frappe.set_route('Form', 'EGC Project Document', row.document)">
									{{ row.document_title || row.document }} (Rev {{ row.revision }})
								</a>
								<button
									v-if="canWrite && current_submission.docstatus === 0"
									type="button"
									class="btn btn-xs btn-default"
									@click="confirm_remove_document(row)"
								>
									{{ __("Remove") }}
								</button>
							</li>
						</ul>
					</section>

					<section v-if="history_submissions.length" class="activity-detail__section">
						<div class="activity-detail__section-title">{{ __("Submission History") }}</div>
						<ul class="activity-detail__list">
							<li v-for="row in history_submissions" :key="row.name">
								<span>{{ row.revision_label }} — {{ format_date(row.date_submitted) }}</span>
								<StatusPill :status="row.response || row.submission_status" />
							</li>
						</ul>
					</section>

					<section class="activity-detail__section">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Related Activities") }}</div>
							<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_link_activity_dialog">
								{{ __("Link Activity") }}
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
					</section>

					<section class="activity-detail__section">
						<div class="activity-detail__section-title">{{ __("Comments") }}</div>
						<EmptyState v-if="!comments.length" :title="__('No comments yet')" />
						<ul v-else class="submittal-comments__list">
							<li v-for="row in comments" :key="row.name" class="submittal-comments__item">
								<div class="submittal-comments__meta">
									<span class="submittal-comments__author">{{ row.owner }}</span>
									<span class="submittal-comments__date">{{ format_datetime(row.creation) }}</span>
								</div>
								<div class="submittal-comments__content">{{ row.content }}</div>
							</li>
						</ul>
						<div class="submittal-comments__composer">
							<textarea
								v-model="new_comment"
								class="form-control"
								rows="2"
								:placeholder="__('Add a comment…')"
							></textarea>
							<button
								type="button"
								class="btn btn-xs btn-primary"
								:disabled="posting_comment || !new_comment.trim()"
								@click="do_post_comment"
							>
								{{ __("Post") }}
							</button>
						</div>
					</section>
				</template>
			</div>
		</div>
	</div>
</template>

<style scoped>
/* Shared detail-drawer shell — deliberately duplicated from ActivityDetail.vue/
   DocumentDetail.vue rather than extracted into a shared file: Vue's `<style scoped>` only
   applies within the component that declares it, and every detail drawer in this Hub already
   keeps its own copy of this shell (`doc-detail__*` in DocumentDetail.vue, `activity-detail__*`
   here and in ActivityDetail.vue) rather than a cross-component stylesheet, so this follows the
   established convention instead of introducing a new one. */
.activity-detail__backdrop {
	position: fixed;
	inset: 0;
	background: rgba(0, 0, 0, 0.35);
	z-index: 500;
	display: flex;
	justify-content: flex-end;
}

.activity-detail__panel {
	width: min(600px, 100vw);
	max-width: 100vw;
	height: 100vh;
	background: var(--fg-color);
	border-left: 1px solid var(--border-color);
	box-shadow: var(--shadow-lg, -4px 0 24px rgba(0, 0, 0, 0.2));
	display: flex;
	flex-direction: column;
	overflow: hidden;
}

.activity-detail__header {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 10px;
	padding: 16px 18px;
	border-bottom: 1px solid var(--border-color);
	flex: 0 0 auto;
}

.activity-detail__code {
	font-size: var(--text-md);
	font-weight: 600;
	color: var(--text-color);
}

.activity-detail__name {
	font-size: var(--text-sm);
	color: var(--text-muted);
	margin-top: 2px;
}

.activity-detail__header-actions {
	display: flex;
	align-items: center;
	gap: 12px;
	flex: 0 0 auto;
}

.activity-detail__close {
	appearance: none;
	border: none;
	background: none;
	font-size: 22px;
	line-height: 1;
	color: var(--text-muted);
	cursor: pointer;
	padding: 2px 4px;
}

.activity-detail__close:hover {
	color: var(--text-color);
}

.activity-detail__body {
	flex: 1 1 auto;
	overflow-y: auto;
	padding: 18px;
	display: flex;
	flex-direction: column;
	gap: 22px;
}

.activity-detail__section-title {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
	margin-bottom: 10px;
}

.activity-detail__head-row {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 10px;
}

.activity-detail__head-row .activity-detail__section-title {
	margin-bottom: 0;
}

.activity-detail__status-row {
	display: flex;
	align-items: center;
	gap: 8px;
	margin-bottom: 12px;
}

.activity-detail__meta {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
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

.activity-detail__section {
	/* No rule needed beyond the body's own flex gap — kept as a named hook so future styling
	   (e.g. a divider) has a single place to land. */
}

.submittal-workflow {
	display: flex;
	flex-direction: column;
	gap: 10px;
	margin: 12px 0;
}

.submittal-workflow__stage {
	display: flex;
	flex-direction: column;
	gap: 4px;
	padding: 8px 10px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
}

.submittal-workflow__step {
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: var(--text-sm);
}

.submittal-workflow__icon {
	width: 16px;
	text-align: center;
	color: var(--text-muted);
}

.submittal-workflow__step--responded .submittal-workflow__icon {
	color: var(--green-500, var(--text-color));
}

.submittal-workflow__step--in-review .submittal-workflow__icon {
	color: var(--blue-500, var(--text-color));
	font-weight: 700;
}

.submittal-workflow__who {
	flex: 1;
	color: var(--text-color);
}

.submittal-workflow__optional {
	color: var(--text-muted);
	font-size: var(--text-xs);
}

.submittal-workflow__response {
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.submittal-comments__list {
	list-style: none;
	margin: 0 0 12px;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.submittal-comments__item {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 8px 12px;
}

.submittal-comments__meta {
	display: flex;
	justify-content: space-between;
	gap: 10px;
	font-size: var(--text-xs);
	color: var(--text-muted);
	margin-bottom: 4px;
}

.submittal-comments__content {
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: pre-wrap;
}

.submittal-comments__composer {
	display: flex;
	flex-direction: column;
	gap: 8px;
	align-items: flex-end;
}

.submittal-comments__composer textarea {
	width: 100%;
	resize: vertical;
}
</style>
