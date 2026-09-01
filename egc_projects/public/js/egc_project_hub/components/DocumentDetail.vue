<!-- Document detail workspace — a full-page view that REPLACES the Documents tab's list
     (DocumentsTab.vue swaps the list out for this, mirroring exactly how SubmittalsTab.vue
     already does it for SubmittalDetail.vue — see that file's own header comment for the
     rationale: "I don't want a side bar I want to have a full screen thing," a standing product
     principle, not a one-off choice). Previously a right-side sliding drawer; moved to full-page
     so a Document can tell its whole story with the same room a Submittal already gets.

     Modeled on SubmittalDetail.vue's own proven shape (status banner → unified chronological
     timeline → sidebar of standing facts) rather than inventing a second detail-page pattern:
     a status banner for "what's true right now and what to do about it," one merged timeline for
     "everything that happened to this document" (every revision uploaded/issued, every related
     Submittal cycle started/responded, comments — interleaved by real timestamp), and a sidebar
     for facts that don't belong in a history feed (current file, metadata, revision register,
     workflow-at-a-glance, related records).

     The "Workflow" sidebar card is the one genuinely new idea, inspired by Aconex's own Doc Mode
     review screen (help.aconex.com: a right-side panel showing completed/current/pending
     workflow steps as a connected chain) — a compact, READ-ONLY preview of the governing
     Submittal's review chain (WorkflowStepper.vue, shared with SubmittalDetail.vue's own
     Reviewers card) so a document's current review progress is visible without leaving the page;
     "Open Submittal" is the escape hatch into the full interactive workflow. -->
<script setup>
import { computed, ref, watch } from "vue";
import {
	get_document_detail,
	create_document_revision,
	submit_document_revision,
	update_revision_readiness,
} from "./documents_api";
import { get_submittal_detail } from "./submittals_api";
import { get_comments, add_comment } from "./comments_api";
import { openSubmitForReviewFlow } from "./submit_for_review_flow";
import { useHubRoute } from "../composables/useHubRoute";
import { openSubmittalIntent } from "../composables/useOpenSubmittalIntent";
import { openActivityIntent } from "../composables/useOpenActivityIntent";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";
import FilePreview from "./FilePreview.vue";
import WorkflowStepper from "./WorkflowStepper.vue";

const props = defineProps({
	document: { type: String, required: true },
});
const emit = defineEmits(["close", "changed"]);

const { data, loading, error, reload } = useHubResource(() => get_document_detail(props.document));
watch(() => props.document, reload, { immediate: true });

function notify_changed() {
	emit("changed");
	reload();
}

function open_form() {
	frappe.set_route("Form", "EGC Project Document", props.document);
}

const { setTab } = useHubRoute();

function open_activity(row) {
	// Into the Hub's own ActivitiesTab/ActivityFullPage, not the raw native form — same reasoning
	// as open_submittal() just below.
	openActivityIntent.activity = row.activity;
	setTab("activities");
}

function open_submittal(row) {
	// Into the Hub's own SubmittalsTab/SubmittalDetail, not the raw native form — see
	// SubmittalDetail.vue's mirroring `open_document()` for the same reasoning.
	openSubmittalIntent.submittal = row.submittal;
	setTab("submittals");
}

// -- bridge into starting a formal review from the document itself: not every document needs
// one, but when it does, this is the obvious place to start it. Uses the same shared flow
// SubmittalsTab.vue's "+ New Submittal" does — the document is preset and locked instead of
// picked, and review setup (ad-hoc reviewer or template) is asked here too.

function open_submit_for_review_dialog() {
	const doc = data.value.document;
	openSubmitForReviewFlow({
		project: doc.project,
		presetDocument: { name: props.document, label: `${doc.document_number} — ${doc.title}` },
		defaults: { title: doc.title, discipline: doc.discipline },
		onCreated(submittal_name) {
			notify_changed();
			frappe.msgprint({
				title: __("Submitted for Review"),
				message: __("Created submittal {0}.", [
					`<a href="#" onclick="frappe.set_route('Form', 'EGC Submittal', '${submittal_name}'); return false;">${frappe.utils.escape_html(submittal_name)}</a>`,
				]),
				indicator: "green",
			});
		},
	});
}

// Mirrors `submittal_control._refresh_from_current`'s own display rule: once a submission has
// been Responded to, its response is the meaningful status, not the generic "Responded" label.
function submittal_row_status(row) {
	return row.submission_status === "Responded" && row.response ? row.response : row.submission_status;
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

function format_datetime(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

const READINESS_VALUES = ["Uploaded", "Reviewed", "Ready to Publish"];

function open_new_revision_dialog() {
	const is_drawing = data.value.document.is_drawing;
	const dialog = new frappe.ui.Dialog({
		title: __("New Revision"),
		fields: [
			{ fieldname: "revision", fieldtype: "Data", label: __("Revision"), reqd: 1 },
			{
				fieldname: "file",
				fieldtype: "Attach",
				label: is_drawing ? __("File (PDF)") : __("File"),
				reqd: 1,
				// ControlAttach.set_upload_options() only fills in doctype/docname/fieldname
				// `if (this.frm)` — a bare frappe.ui.Dialog has no bound form, so without this
				// explicit `options` override every file uploaded here would land as an orphaned
				// File record (null attached_to_doctype). The revision itself doesn't exist yet
				// at upload time, so the file is attached to the parent Document's own
				// `current_file` field instead — the field this same URL will end up holding
				// once the revision is issued.
				options: { doctype: "EGC Project Document", docname: props.document, fieldname: "current_file" },
			},
			...(is_drawing
				? [
						{
							fieldname: "native_file",
							fieldtype: "Attach",
							label: __("Native File (e.g. .dwg)"),
							description: __("Optional — the native authoring file, same revision as File above."),
							options: { doctype: "EGC Project Document", docname: props.document, fieldname: "current_file" },
						},
					]
				: []),
			{
				fieldname: "revision_date",
				fieldtype: "Date",
				label: __("Revision Date"),
				default: frappe.datetime.get_today(),
			},
			{ fieldname: "reason_for_revision", fieldtype: "Data", label: __("Reason for Revision") },
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
			{
				fieldname: "readiness",
				fieldtype: "Select",
				label: __("Readiness"),
				options: READINESS_VALUES,
				default: "Uploaded",
			},
		],
		primary_action_label: __("Create Revision"),
		primary_action(values) {
			create_document_revision({
				document: props.document,
				revision: values.revision,
				file: values.file,
				native_file: values.native_file || undefined,
				revision_date: values.revision_date,
				reason_for_revision: values.reason_for_revision,
				remarks: values.remarks,
				readiness: values.readiness,
			})
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Create Revision"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_issue(rev) {
	// Wording deliberately matches `egc_project_document_revision.js`'s own `frm.set_intro`
	// warning, so the Hub never says something softer than the native form does about the same
	// irreversible act.
	const message = __(
		"Issue revision {0}? Submitting it issues the revision permanently: the file can never be replaced afterwards, and any previously current revision of this document becomes Superseded. This cannot be undone.",
		[rev.revision]
	);
	frappe.confirm(message, () => issue_revision(rev));
}

function issue_revision(rev) {
	submit_document_revision(rev.name).then(notify_changed).catch((e) => {
		frappe.msgprint({ title: __("Could Not Issue Revision"), message: e.message, indicator: "red" });
	});
}

// -- inline preview: toggled per row, and once for the "Current File" summary -------------------

const preview_open = ref(new Set());

function toggle_preview(key) {
	const next = new Set(preview_open.value);
	if (next.has(key)) {
		next.delete(key);
	} else {
		next.add(key);
	}
	preview_open.value = next;
}

function do_update_readiness(rev, event) {
	update_revision_readiness(rev.name, event.target.value)
		.then(notify_changed)
		.catch((e) => {
			event.target.value = rev.readiness;
			frappe.msgprint({ title: __("Could Not Update Readiness"), message: e.message, indicator: "red" });
		});
}

// -- compare revisions -----------------------------------------------------------------------
// Exactly two revisions side by side — a third pick bumps the OLDEST of the current two, so the
// comparison always stays meaningful without forcing a manual deselect first.

const compare_mode = ref(false);
const compare_selection = ref([]);

function toggle_compare_mode() {
	compare_mode.value = !compare_mode.value;
	compare_selection.value = [];
}

function toggle_compare_pick(rev_name) {
	const next = [...compare_selection.value];
	const index = next.indexOf(rev_name);
	if (index !== -1) {
		next.splice(index, 1);
	} else {
		next.push(rev_name);
		if (next.length > 2) next.shift();
	}
	compare_selection.value = next;
}

function compare_rev(rev_name) {
	return (data.value?.revisions || []).find((r) => r.name === rev_name);
}

// -- status banner: "what's true right now, what's next" — same role as SubmittalDetail.vue's
// own banner, computed from the document/approval status pair instead of a submission cycle. ---

const latest_draft_revision = computed(() => (data.value?.revisions || []).find((r) => r.docstatus === 0) || null);

// Mirrors `document_control.assert_new_revision_allowed`'s backend rule exactly: once a document
// has a current (Issued) revision, a new one is only allowed while that revision is genuinely
// open to being superseded — never submitted, or sent back by a reviewer. A revision Draft
// already sitting unissued (`latest_draft_revision`) blocks it too — issue or discard that one
// first rather than stacking a second Draft on top of it.
const can_add_revision = computed(() => {
	const d = data.value?.document;
	if (!d || latest_draft_revision.value) return false;
	if (!d.current_revision) return true;
	return ["Not Submitted", "Revise & Resubmit", "Rejected"].includes(d.approval_status);
});

// `data.document.current_file` mirrors the current revision's `file` directly, but there's no
// equivalent mirrored field for `native_file` (a Drawing-only, paired-attachment concept, not
// worth a second mirrored column on the Document itself) — looked up from the revision list
// instead, which already flags which row is current.
const current_revision_native_file = computed(
	() => (data.value?.revisions || []).find((r) => r.is_current)?.native_file || null
);

const banner_tone = computed(() => {
	const d = data.value?.document;
	if (!d) return "grey";
	if (["Approved", "Approved with Comments"].includes(d.approval_status)) return "green";
	if (d.approval_status === "Rejected") return "red";
	if (d.approval_status === "Revise & Resubmit") return "orange";
	if (d.approval_status === "Under Review") return "blue";
	return "grey";
});

const current_related_submittal = computed(() => (data.value?.submittals || [])[0] || null);

const banner_text = computed(() => {
	const d = data.value?.document;
	if (!d) return "";
	if (!d.current_revision) {
		return latest_draft_revision.value
			? __("Rev {0} uploaded — issue it when ready to make it the current revision.", [latest_draft_revision.value.revision])
			: __("No revision uploaded yet — add the first one to get started.");
	}
	if (d.approval_status === "Not Submitted") {
		return __("Rev {0} issued — no review requested yet. Submit for review if this document needs sign-off.", [d.current_revision_label]);
	}
	if (d.approval_status === "Under Review") {
		const rel = current_related_submittal.value;
		return rel?.ball_in_court
			? __("Awaiting {0} to respond.", [rel.ball_in_court])
			: __("Under review — see the Workflow panel for who owes the next action.");
	}
	if (["Approved", "Approved with Comments"].includes(d.approval_status)) {
		return __("{0} — no action needed.", [d.approval_status]);
	}
	if (["Revise & Resubmit", "Rejected"].includes(d.approval_status)) {
		const rel = current_related_submittal.value;
		return rel?.response ? __("{0} — issue a new revision to address it.", [rel.response]) : d.approval_status;
	}
	return d.approval_status;
});

const rejection_reason_text = computed(() => {
	const d = data.value?.document;
	const rel = current_related_submittal.value;
	if (!d || !rel || !["Revise & Resubmit", "Rejected"].includes(d.approval_status)) return null;
	return rel.response_remarks || null;
});

// -- Workflow card: a compact, read-only preview of the governing Submittal's review chain
// (Aconex's own Doc Mode screen shows the same idea as a right-side "Workflow Steps" panel) —
// lazily fetches that ONE Submittal's full detail (reusing get_submittal_detail, no new
// endpoint) only when a related Submittal actually exists. -------------------------------------

const workflow_submittal = ref(null);
const workflow_loading = ref(false);

async function load_workflow() {
	workflow_submittal.value = null;
	const rel = current_related_submittal.value;
	if (!rel) return;
	workflow_loading.value = true;
	try {
		workflow_submittal.value = await get_submittal_detail(rel.submittal);
	} catch (e) {
		workflow_submittal.value = null;
	} finally {
		workflow_loading.value = false;
	}
}
watch(() => current_related_submittal.value?.submittal_revision, load_workflow, { immediate: true });

const workflow_submission = computed(() => {
	const rel = current_related_submittal.value;
	if (!rel || !workflow_submittal.value) return null;
	const submissions = workflow_submittal.value.submissions || [];
	return submissions.find((s) => s.name === rel.submittal_revision) || submissions[0] || null;
});

const workflow_stages = computed(() => {
	const steps = workflow_submission.value?.steps || [];
	const by_sequence = {};
	for (const step of steps) {
		(by_sequence[step.sequence] = by_sequence[step.sequence] || []).push(step);
	}
	return Object.keys(by_sequence)
		.map(Number)
		.sort((a, b) => a - b)
		.map((seq) => ({ sequence: seq, steps: by_sequence[seq] }));
});

// -- comments (generic thread, same doctype-agnostic module SubmittalDetail.vue uses) — rendered
// as part of the unified timeline below, not a separate box. ------------------------------------

const comments = ref([]);
const new_comment = ref("");
const posting_comment = ref(false);

async function load_comments() {
	try {
		comments.value = await get_comments("EGC Project Document", props.document);
	} catch (e) {
		comments.value = [];
	}
}
watch(() => props.document, load_comments, { immediate: true });

async function do_post_comment() {
	if (!new_comment.value.trim()) return;
	posting_comment.value = true;
	try {
		await add_comment("EGC Project Document", props.document, new_comment.value);
		new_comment.value = "";
		await load_comments();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Post Comment"), message: e.message, indicator: "red" });
	} finally {
		posting_comment.value = false;
	}
}

// -- unified timeline: every revision uploaded/issued, every related Submittal cycle
// started/responded, and comments, merged into ONE chronological feed. Simpler than
// SubmittalDetail.vue's own bucket-interleaving version: every event type here now carries a
// real Datetime (`creation`/`modified`, added to get_revisions()/_related_submittals() alongside
// this redesign specifically so this page could do a plain global sort instead). -----------------

function event_tone(event) {
	if (event.type === "revision_issued") return "blue";
	if (event.type === "submitted") return "blue";
	if (event.type === "responded") {
		if (["Approved", "Approved with Comments"].includes(event.submittal.response)) return "green";
		if (event.submittal.response === "Rejected") return "red";
		if (event.submittal.response === "Revise & Resubmit") return "orange";
	}
	return "grey";
}

function event_icon(event) {
	if (event.type === "revision_created") return "+";
	if (event.type === "revision_issued") return "↑";
	if (event.type === "submitted") return "→";
	if (event.type === "comment") return "●";
	if (event.type === "responded") {
		if (["Approved", "Approved with Comments"].includes(event.submittal.response)) return "✓";
		if (event.submittal.response === "Rejected") return "✕";
		if (event.submittal.response === "Revise & Resubmit") return "↺";
	}
	return "○";
}

const timeline_events = computed(() => {
	const events = [];

	for (const rev of [...(data.value?.revisions || [])].reverse()) {
		events.push({ type: "revision_created", key: `${rev.name}-created`, timestamp: rev.creation, rev });
		if (rev.docstatus === 1) {
			events.push({ type: "revision_issued", key: `${rev.name}-issued`, timestamp: rev.issue_date || rev.modified, rev });
		}
	}

	for (const s of [...(data.value?.submittals || [])].reverse()) {
		events.push({ type: "submitted", key: `${s.submittal_revision}-submitted`, timestamp: s.creation, submittal: s });
		if (s.submission_status === "Responded" && s.response) {
			events.push({
				type: "responded",
				key: `${s.submittal_revision}-responded`,
				timestamp: s.modified,
				submittal: s,
			});
		}
	}

	for (const c of comments.value) {
		events.push({ type: "comment", key: `comment-${c.name}`, timestamp: c.creation, comment: c });
	}

	return events.sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
});
</script>

<template>
	<div class="doc-page">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />

		<template v-else-if="data">
			<div class="doc-page__topbar">
				<a href="#" class="hub-link doc-page__back" @click.prevent="$emit('close')">
					{{ __("← Back to Documents") }}
				</a>
				<div class="doc-page__topbar-actions">
					<a href="#" class="hub-link hub-link--muted" @click.prevent="open_form">
						{{ __("View raw record ↗") }}
					</a>
				</div>
			</div>

			<div class="doc-page__identity">
				<div class="doc-page__code">{{ data.document.document_number }}</div>
				<h1 class="doc-page__title">{{ data.document.title }}</h1>
				<div class="doc-page__status-row">
					<StatusPill :status="data.document.document_status" />
					<StatusPill :status="data.document.approval_status" />
					<span class="doc-page__meta-inline">
						{{ data.document.document_type
						}}<template v-if="data.document.discipline"> · {{ data.document.discipline }}</template>
					</span>
				</div>
			</div>

			<div class="submittal-banner" :class="`submittal-banner--${banner_tone}`">
				<div class="submittal-banner__main">
					<p class="submittal-banner__text">{{ banner_text }}</p>
					<div v-if="rejection_reason_text" class="submittal-banner__reason">
						<span class="submittal-banner__reason-label">{{ current_related_submittal.response }}:</span>
						{{ rejection_reason_text }}
					</div>
				</div>
				<div class="submittal-banner__actions">
					<button
						v-if="latest_draft_revision"
						type="button"
						class="btn btn-sm btn-primary"
						@click="confirm_issue(latest_draft_revision)"
					>
						{{ __("Issue Rev {0}", [latest_draft_revision.revision]) }}
					</button>
					<button
						v-if="data.document.current_revision && data.document.approval_status === 'Not Submitted'"
						type="button"
						class="btn btn-sm btn-primary"
						@click="open_submit_for_review_dialog"
					>
						{{ __("Submit for Review") }}
					</button>
					<button
						v-if="can_add_revision && ['Revise & Resubmit', 'Rejected'].includes(data.document.approval_status)"
						type="button"
						class="btn btn-sm btn-primary"
						@click="open_new_revision_dialog"
					>
						{{ __("New Revision") }}
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
								<template v-if="event.type === 'revision_created'">
									<p class="submittal-timeline__headline">
										<strong>{{ __("Rev {0}", [event.rev.revision]) }}</strong> {{ __("uploaded") }}
										<span class="submittal-timeline__when">{{ format_datetime(event.timestamp) }}</span>
									</p>
									<p v-if="event.rev.reason_for_revision" class="submittal-timeline__remarks">
										{{ event.rev.reason_for_revision }}
									</p>
								</template>

								<template v-else-if="event.type === 'revision_issued'">
									<p class="submittal-timeline__headline">
										<strong>{{ __("Rev {0}", [event.rev.revision]) }}</strong> {{ __("issued — now current") }}
										<span class="submittal-timeline__when">{{ format_datetime(event.timestamp) }}</span>
									</p>
								</template>

								<template v-else-if="event.type === 'submitted'">
									<p class="submittal-timeline__headline">
										{{ __("Submitted for review via") }}
										<a href="#" class="hub-link" @click.prevent="open_submittal(event.submittal)">
											{{ event.submittal.submittal_number }}
										</a>
										<span class="submittal-timeline__when">{{ format_datetime(event.timestamp) }}</span>
									</p>
								</template>

								<template v-else-if="event.type === 'responded'">
									<p class="submittal-timeline__headline">
										<a href="#" class="hub-link" @click.prevent="open_submittal(event.submittal)">
											{{ event.submittal.submittal_number }}
										</a>
										<span class="indicator-pill" :class="event_tone(event)">{{ event.submittal.response }}</span>
										<span class="submittal-timeline__when">{{ format_datetime(event.timestamp) }}</span>
									</p>
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
						<EmptyState v-if="!timeline_events.length" :title="__('Nothing has happened yet')" />
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
						<div class="activity-detail__section-title">{{ __("Current File") }}</div>
						<template v-if="data.document.current_file">
							<div class="doc-sidebar__file-row">
								<a class="hub-link" href="#" @click.prevent="toggle_preview('current')">
									{{ preview_open.has('current') ? __("Hide Preview") : __("Preview") }}
								</a>
								<a :href="data.document.current_file" target="_blank" rel="noopener" class="hub-link">
									{{ __("Open") }}
								</a>
							</div>
							<FilePreview
								v-if="preview_open.has('current')"
								:file-url="data.document.current_file"
								:file-name="data.document.document_number"
							/>
							<div v-if="current_revision_native_file" class="doc-sidebar__file-row">
								<span class="doc-sidebar__native-label">{{ __("Native File") }}:</span>
								<a :href="current_revision_native_file" target="_blank" rel="noopener" class="hub-link">
									{{ __("Open") }}
								</a>
							</div>
						</template>
						<EmptyState v-else :title="__('No revision issued yet')" />
					</div>

					<div class="submittal-sidebar__card">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Workflow") }}</div>
							<a
								v-if="current_related_submittal"
								href="#"
								class="hub-link"
								@click.prevent="open_submittal(current_related_submittal)"
							>
								{{ __("Open") }}
							</a>
						</div>
						<template v-if="current_related_submittal">
							<div class="doc-workflow__line">
								<span class="doc-workflow__number">{{ current_related_submittal.submittal_number }}</span>
								<StatusPill :status="submittal_row_status(current_related_submittal)" />
							</div>
							<LoadingState v-if="workflow_loading" :rows="2" />
							<WorkflowStepper v-else-if="workflow_stages.length" :stages="workflow_stages" compact />
							<p v-else class="doc-sidebar__hint">{{ __("No formal review steps on this cycle.") }}</p>
						</template>
						<EmptyState
							v-else
							:title="__('No review requested yet')"
							:action-label="data.document.current_revision ? __('Submit for Review') : ''"
							@action="open_submit_for_review_dialog"
						/>
					</div>

					<div class="submittal-sidebar__card">
						<div class="activity-detail__section-title">{{ __("Metadata") }}</div>
						<dl class="activity-detail__meta submittal-sidebar__meta">
							<div>
								<dt>{{ __("Originator") }}</dt>
								<dd>{{ data.document.originator || "—" }}</dd>
							</div>
							<div>
								<dt>{{ __("WBS Node") }}</dt>
								<dd>{{ data.document.wbs_node || "—" }}</dd>
							</div>
						</dl>
						<p v-if="data.document.description" class="doc-sidebar__description">{{ data.document.description }}</p>
						<dl v-if="data.document.is_drawing" class="activity-detail__meta submittal-sidebar__meta doc-sidebar__drawing-meta">
							<div>
								<dt>{{ __("Drawing Set") }}</dt>
								<dd>{{ data.document.drawing_set || "—" }}</dd>
							</div>
							<div>
								<dt>{{ __("Drawing Area") }}</dt>
								<dd>{{ data.document.drawing_area || "—" }}</dd>
							</div>
							<div>
								<dt>{{ __("Drawing Date") }}</dt>
								<dd>{{ format_date(data.document.drawing_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Received Date") }}</dt>
								<dd>{{ format_date(data.document.received_date) }}</dd>
							</div>
						</dl>
					</div>

					<div class="submittal-sidebar__card">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Revision Register") }}</div>
							<div class="doc-sidebar__head-actions">
								<button
									v-if="data.revisions.length > 1"
									type="button"
									class="btn btn-xs"
									:class="compare_mode ? 'btn-primary' : 'btn-default'"
									@click="toggle_compare_mode"
								>
									{{ compare_mode ? __("Cancel") : __("Compare") }}
								</button>
								<button
									v-if="can_add_revision"
									type="button"
									class="btn btn-xs btn-default"
									@click="open_new_revision_dialog"
								>
									{{ __("New") }}
								</button>
							</div>
						</div>
						<EmptyState v-if="!data.revisions.length" :title="__('No revisions recorded yet')" />
						<template v-else>
							<p v-if="compare_mode" class="doc-sidebar__hint">
								{{ __("Pick two revisions to compare.") }}
							</p>
							<div v-for="rev in data.revisions" :key="rev.name" class="doc-revision-row">
								<input
									v-if="compare_mode"
									type="checkbox"
									:checked="compare_selection.includes(rev.name)"
									:disabled="!rev.file"
									@change="toggle_compare_pick(rev.name)"
								/>
								<div class="doc-revision-row__main">
									<div class="doc-revision-row__head">
										<span class="doc-revision-row__label">
											{{ __("Rev {0}", [rev.revision]) }}
											<span v-if="rev.is_current" class="doc-detail__current-badge">{{ __("Current") }}</span>
										</span>
										<StatusPill :status="rev.revision_status" />
									</div>
									<div class="doc-revision-row__meta">
										<span>{{ format_date(rev.revision_date) }}</span>
										<select
											v-if="rev.docstatus === 0"
											class="doc-detail__readiness-select"
											:value="rev.readiness"
											@change="do_update_readiness(rev, $event)"
										>
											<option v-for="value in READINESS_VALUES" :key="value" :value="value">{{ value }}</option>
										</select>
										<span v-else-if="rev.readiness">{{ rev.readiness }}</span>
										<a v-if="rev.file" href="#" class="hub-link" @click.prevent="toggle_preview(rev.name)">
											{{ preview_open.has(rev.name) ? __("Hide") : __("Preview") }}
										</a>
										<a v-if="rev.native_file" :href="rev.native_file" target="_blank" rel="noopener" class="hub-link">
											{{ __("Native File") }}
										</a>
										<button
											v-if="rev.docstatus === 0"
											type="button"
											class="btn btn-xs btn-default"
											@click="confirm_issue(rev)"
										>
											{{ __("Issue") }}
										</button>
									</div>
									<FilePreview v-if="preview_open.has(rev.name)" :file-url="rev.file" :file-name="rev.revision" />
								</div>
							</div>

							<div v-if="compare_mode && compare_selection.length === 2" class="doc-detail__compare-panel">
								<div v-for="rev_name in compare_selection" :key="rev_name" class="doc-detail__compare-side">
									<div class="doc-detail__compare-side-title">
										{{ __("Revision") }} {{ compare_rev(rev_name)?.revision }}
									</div>
									<FilePreview :file-url="compare_rev(rev_name)?.file" :file-name="compare_rev(rev_name)?.revision" />
								</div>
							</div>
						</template>
					</div>

					<div class="submittal-sidebar__card">
						<div class="activity-detail__section-title">{{ __("Related Activities") }}</div>
						<EmptyState v-if="!data.activities.length" :title="__('No linked activities yet')" />
						<ul v-else class="activity-detail__list">
							<li v-for="a in data.activities" :key="a.name">
								<a href="#" class="activity-detail__link" @click.prevent="open_activity(a)">
									{{ a.activity_code }} — {{ a.activity_name }}
								</a>
								<StatusPill :status="a.status" />
							</li>
						</ul>
					</div>

					<div class="submittal-sidebar__card">
						<div class="activity-detail__section-title">{{ __("Related Submittals") }}</div>
						<EmptyState v-if="!data.submittals.length" :title="__('No related submittals')" />
						<ul v-else class="activity-detail__list">
							<li v-for="s in data.submittals" :key="s.submittal_revision">
								<a href="#" class="activity-detail__link" @click.prevent="open_submittal(s)">
									{{ s.submittal_number }} — {{ s.submittal_title }} (S{{ s.revision_label }})
								</a>
								<StatusPill :status="submittal_row_status(s)" />
							</li>
						</ul>
					</div>
				</div>
			</div>
		</template>
	</div>
</template>

<style scoped>
.doc-page {
	display: flex;
	flex-direction: column;
	gap: 18px;
}

.doc-page__topbar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
}

.doc-page__back {
	font-weight: 500;
}

.doc-page__topbar-actions {
	display: flex;
	align-items: center;
	gap: 14px;
}

.hub-link--muted {
	color: var(--text-muted);
	font-size: var(--text-xs);
}

.doc-page__identity {
	border-bottom: 1px solid var(--border-color);
	padding-bottom: 16px;
}

.doc-page__code {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-muted);
}

.doc-page__title {
	font-size: var(--text-2xl, 22px);
	font-weight: 600;
	color: var(--text-color);
	margin: 2px 0 10px;
}

.doc-page__status-row {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 8px 12px;
}

.doc-page__meta-inline {
	font-size: var(--text-sm);
	color: var(--text-muted);
}

/* Banner/timeline/sidebar shell reuses SubmittalDetail.vue's exact class names — Vue `<style
   scoped>` isolates both components' rules by their own data attribute, so there is no
   collision, and any future visual tweak to the shared "page shell" language only needs to
   change in one mental model even though it's two separate scoped blocks. */
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

.submittal-timeline__when {
	color: var(--text-muted);
	font-size: var(--text-xs);
	margin-left: auto;
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
	border-radius: var(--border-radius);
	padding: 14px;
}

.submittal-sidebar__meta {
	margin-top: 8px;
}

.doc-sidebar__file-row {
	display: flex;
	align-items: center;
	gap: 12px;
	margin-top: 6px;
	font-size: var(--text-sm);
}

.doc-sidebar__native-label {
	color: var(--text-muted);
}

.doc-sidebar__head-actions {
	display: flex;
	gap: 6px;
}

.doc-sidebar__hint {
	font-size: var(--text-xs);
	color: var(--text-muted);
	margin: 6px 0 0;
}

.doc-sidebar__description {
	margin: 10px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: pre-wrap;
}

.doc-sidebar__drawing-meta {
	margin-top: 12px;
	padding-top: 12px;
	border-top: 1px dashed var(--border-color);
}

.doc-workflow__line {
	display: flex;
	align-items: center;
	gap: 8px;
	margin-bottom: 10px;
}

.doc-workflow__number {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
}

.doc-revision-row {
	display: flex;
	gap: 8px;
	padding: 8px 0;
	border-top: 1px solid var(--border-color);
}

.doc-revision-row:first-of-type {
	border-top: none;
	padding-top: 0;
}

.doc-revision-row__main {
	flex: 1 1 auto;
	min-width: 0;
}

.doc-revision-row__head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 8px;
}

.doc-revision-row__label {
	font-size: var(--text-sm);
	font-weight: 500;
	color: var(--text-color);
}

.doc-revision-row__meta {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 10px;
	margin-top: 4px;
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.doc-detail__readiness-select {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	color: var(--text-color);
	padding: 2px 5px;
	font-size: var(--text-xs);
}

.doc-detail__current-badge {
	margin-left: 6px;
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--dark-green-500, var(--green-500));
}

.doc-detail__compare-panel {
	display: flex;
	flex-wrap: wrap;
	gap: 12px;
	margin-top: 14px;
}

.doc-detail__compare-side {
	flex: 1 1 240px;
	min-width: 0;
}

.doc-detail__compare-side-title {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
	margin-bottom: 8px;
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
	padding: 8px 10px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	font-size: var(--text-sm);
}

.activity-detail__link {
	color: var(--text-color);
	cursor: pointer;
	text-decoration: none;
	border-bottom: 1px dashed var(--border-color);
}

.hub-link {
	color: var(--text-color);
	cursor: pointer;
	text-decoration: none;
	border-bottom: 1px dashed var(--border-color);
}

.hub-link:hover {
	border-bottom-color: var(--text-color);
}
</style>
