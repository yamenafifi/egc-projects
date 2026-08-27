<script setup>
import { ref, watch } from "vue";
import {
	get_document_detail,
	create_document_revision,
	submit_document_revision,
	update_revision_readiness,
} from "./documents_api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";
import FilePreview from "./FilePreview.vue";

const props = defineProps({
	document: { type: String, required: true },
});
const emit = defineEmits(["close", "changed"]);

const { data, loading, error, reload } = useHubResource(() => get_document_detail(props.document));
watch(() => props.document, reload, { immediate: true });

function open_form() {
	frappe.set_route("Form", "EGC Project Document", props.document);
}

function open_activity(row) {
	frappe.set_route("Form", "EGC Activity", row.activity);
}

function open_submittal(row) {
	frappe.set_route("Form", "EGC Submittal", row.submittal);
}

// Mirrors `submittal_control._refresh_from_current`'s own display rule: once a submission has
// been Responded to, its response is the meaningful status, not the generic "Responded" label.
function submittal_row_status(row) {
	return row.submission_status === "Responded" && row.response ? row.response : row.submission_status;
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

function open_new_revision_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("New Revision"),
		fields: [
			{ fieldname: "revision", fieldtype: "Data", label: __("Revision"), reqd: 1 },
			{
				fieldname: "file",
				fieldtype: "Attach",
				label: __("File"),
				reqd: 1,
				// ControlAttach.set_upload_options() only fills in doctype/docname/fieldname
				// `if (this.frm)` — a bare frappe.ui.Dialog has no bound form, so without this
				// explicit `options` override every file uploaded here would land as an orphaned
				// File record (null attached_to_doctype), invisible to /app/file and to any
				// attached_to_*-filtered query or private-file permission check. The revision
				// itself doesn't exist yet at upload time (it's created after this dialog
				// submits), so the file is attached to the parent Document's own `current_file`
				// field instead — the field that will end up holding this same URL once the
				// revision is issued.
				options: { doctype: "EGC Project Document", docname: props.document, fieldname: "current_file" },
			},
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
				revision_date: values.revision_date,
				reason_for_revision: values.reason_for_revision,
				remarks: values.remarks,
				readiness: values.readiness,
			})
				.then(() => {
					dialog.hide();
					reload();
					emit("changed");
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
	submit_document_revision(rev.name)
		.then(() => {
			reload();
			emit("changed");
		})
		.catch((e) => {
			frappe.msgprint({ title: __("Could Not Issue Revision"), message: e.message, indicator: "red" });
		});
}

const READINESS_VALUES = ["Uploaded", "Reviewed", "Ready to Publish"];

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
		.then(() => {
			reload();
			emit("changed");
		})
		.catch((e) => {
			event.target.value = rev.readiness;
			frappe.msgprint({ title: __("Could Not Update Readiness"), message: e.message, indicator: "red" });
		});
}

// -- compare revisions (Level 1 §34) -----------------------------------------------------------
// Exactly two revisions side by side — a third pick bumps the OLDEST of the current two, so the
// comparison always stays meaningful (two specific revisions, not an accumulating pile) without
// forcing the user to manually deselect first.

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
</script>

<template>
	<div class="doc-detail__backdrop" @click.self="$emit('close')">
		<div class="doc-detail__panel" role="dialog" aria-modal="true">
			<div class="doc-detail__header">
				<div class="doc-detail__identity">
					<div class="doc-detail__number">{{ data?.document?.document_number || document }}</div>
					<div class="doc-detail__title">{{ data?.document?.title || "" }}</div>
				</div>
				<div class="doc-detail__header-actions">
					<a href="#" class="hub-link" @click.prevent="open_form">{{ __("Open Form") }}</a>
					<button type="button" class="doc-detail__close" :aria-label="__('Close')" @click="$emit('close')">
						&times;
					</button>
				</div>
			</div>

			<div class="doc-detail__body">
				<LoadingState v-if="loading" :rows="6" />
				<ErrorState v-else-if="error" :message="error" @retry="reload" />

				<template v-else-if="data">
					<section class="doc-detail__section">
						<div class="doc-detail__status-row">
							<StatusPill :status="data.document.document_status" />
							<StatusPill :status="data.document.approval_status" />
						</div>
						<dl class="doc-detail__meta">
							<div>
								<dt>{{ __("Document Type") }}</dt>
								<dd>{{ data.document.document_type }}</dd>
							</div>
							<div>
								<dt>{{ __("Discipline") }}</dt>
								<dd>{{ data.document.discipline || "—" }}</dd>
							</div>
							<div>
								<dt>{{ __("Originator") }}</dt>
								<dd>{{ data.document.originator || "—" }}</dd>
							</div>
							<div>
								<dt>{{ __("WBS Node") }}</dt>
								<dd>{{ data.document.wbs_node || "—" }}</dd>
							</div>
						</dl>
						<div v-if="data.document.description" class="doc-detail__description">
							{{ data.document.description }}
						</div>
						<dl v-if="data.document.is_drawing" class="doc-detail__meta doc-detail__meta--drawing">
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
						<div class="doc-detail__file">
							<span class="doc-detail__meta-label">{{ __("Current File") }}:</span>
							<template v-if="data.document.current_file">
								<a class="hub-link" href="#" @click.prevent="toggle_preview('current')">
									{{ preview_open.has('current') ? __("Hide Preview") : __("Preview") }}
								</a>
								<a
									:href="data.document.current_file"
									target="_blank"
									rel="noopener"
									class="hub-link doc-detail__open-link"
								>
									{{ __("Open") }}
								</a>
							</template>
							<span v-else class="text-muted">{{ __("No revision issued yet") }}</span>
						</div>
						<FilePreview
							v-if="preview_open.has('current')"
							:file-url="data.document.current_file"
							:file-name="data.document.document_number"
						/>
					</section>

					<section class="doc-detail__section">
						<div class="doc-detail__section-head">
							<div class="doc-detail__section-title">{{ __("Revision History") }}</div>
							<div class="doc-detail__section-head-actions">
								<button
									v-if="data.revisions.length > 1"
									type="button"
									class="btn btn-xs"
									:class="compare_mode ? 'btn-primary' : 'btn-default'"
									@click="toggle_compare_mode"
								>
									{{ compare_mode ? __("Cancel Compare") : __("Compare Revisions") }}
								</button>
								<button type="button" class="btn btn-xs btn-default" @click="open_new_revision_dialog">
									{{ __("New Revision") }}
								</button>
							</div>
						</div>
						<EmptyState v-if="!data.revisions.length" :title="__('No revisions recorded yet')" />
						<template v-else>
							<p v-if="compare_mode" class="doc-detail__compare-hint">
								{{ __("Pick two revisions to compare — picking a third drops the oldest of the current pair.") }}
							</p>
							<div class="hub-table-wrap">
								<table class="hub-table">
									<thead>
										<tr>
											<th v-if="compare_mode"></th>
											<th>{{ __("Revision") }}</th>
											<th>{{ __("Status") }}</th>
											<th>{{ __("Readiness") }}</th>
											<th>{{ __("Revision Date") }}</th>
											<th>{{ __("Issue Date") }}</th>
											<th>{{ __("File") }}</th>
											<th>{{ __("Remarks") }}</th>
											<th></th>
										</tr>
									</thead>
									<tbody>
										<template v-for="rev in data.revisions" :key="rev.name">
											<tr>
												<td v-if="compare_mode">
													<input
														type="checkbox"
														:checked="compare_selection.includes(rev.name)"
														:disabled="!rev.file"
														@change="toggle_compare_pick(rev.name)"
													/>
												</td>
												<td>
													{{ rev.revision }}
													<span v-if="rev.is_current" class="doc-detail__current-badge">{{ __("Current") }}</span>
												</td>
												<td><StatusPill :status="rev.revision_status" /></td>
												<td>
													<select
														v-if="rev.docstatus === 0"
														class="doc-detail__readiness-select"
														:value="rev.readiness"
														@change="do_update_readiness(rev, $event)"
													>
														<option v-for="value in READINESS_VALUES" :key="value" :value="value">{{ value }}</option>
													</select>
													<span v-else>{{ rev.readiness || "—" }}</span>
												</td>
												<td>{{ format_date(rev.revision_date) }}</td>
												<td>{{ rev.issue_date ? format_date(rev.issue_date) : "—" }}</td>
												<td>
													<a v-if="rev.file" href="#" class="hub-link" @click.prevent="toggle_preview(rev.name)">
														{{ preview_open.has(rev.name) ? __("Hide") : __("Preview") }}
													</a>
													<span v-else>—</span>
												</td>
												<td>{{ rev.remarks || "—" }}</td>
												<td>
													<button
														v-if="rev.docstatus === 0"
														type="button"
														class="btn btn-xs btn-default"
														@click="confirm_issue(rev)"
													>
														{{ __("Issue") }}
													</button>
												</td>
											</tr>
											<tr v-if="preview_open.has(rev.name)">
												<td :colspan="compare_mode ? 9 : 8" class="doc-detail__preview-cell">
													<FilePreview :file-url="rev.file" :file-name="rev.revision" />
												</td>
											</tr>
										</template>
									</tbody>
								</table>
							</div>

							<div v-if="compare_mode && compare_selection.length === 2" class="doc-detail__compare-panel">
								<div v-for="rev_name in compare_selection" :key="rev_name" class="doc-detail__compare-side">
									<div class="doc-detail__compare-side-title">
										{{ __("Revision") }} {{ compare_rev(rev_name)?.revision }}
										<span v-if="compare_rev(rev_name)?.is_current" class="doc-detail__current-badge">{{ __("Current") }}</span>
									</div>
									<FilePreview :file-url="compare_rev(rev_name)?.file" :file-name="compare_rev(rev_name)?.revision" />
								</div>
							</div>
						</template>
					</section>

					<section class="doc-detail__section">
						<div class="doc-detail__section-title">{{ __("Related Activities") }}</div>
						<EmptyState v-if="!data.activities.length" :title="__('No related activities')" />
						<ul v-else class="doc-detail__list">
							<li v-for="a in data.activities" :key="a.name">
								<a href="#" class="hub-link" @click.prevent="open_activity(a)">
									{{ a.activity_code }} — {{ a.activity_name }}
								</a>
								<StatusPill :status="a.status" />
							</li>
						</ul>
					</section>

					<section class="doc-detail__section">
						<div class="doc-detail__section-title">{{ __("Related Submittals") }}</div>
						<EmptyState v-if="!data.submittals.length" :title="__('No related submittals')" />
						<ul v-else class="doc-detail__list">
							<li v-for="s in data.submittals" :key="s.submittal_revision">
								<a href="#" class="hub-link" @click.prevent="open_submittal(s)">
									{{ s.submittal_number }} — {{ s.submittal_title }} (S{{ s.revision_label }})
								</a>
								<StatusPill :status="submittal_row_status(s)" />
							</li>
						</ul>
					</section>
				</template>
			</div>
		</div>
	</div>
</template>

<style scoped>
.doc-detail__backdrop {
	position: fixed;
	inset: 0;
	background: rgba(0, 0, 0, 0.35);
	z-index: 500;
	display: flex;
	justify-content: flex-end;
}

.doc-detail__panel {
	width: min(560px, 100vw);
	max-width: 100vw;
	height: 100vh;
	background: var(--fg-color);
	border-left: 1px solid var(--border-color);
	box-shadow: var(--shadow-lg, -4px 0 24px rgba(0, 0, 0, 0.2));
	display: flex;
	flex-direction: column;
	overflow: hidden;
}

.doc-detail__header {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 10px;
	padding: 16px 18px;
	border-bottom: 1px solid var(--border-color);
	flex: 0 0 auto;
}

.doc-detail__number {
	font-size: var(--text-md);
	font-weight: 600;
	color: var(--text-color);
}

.doc-detail__title {
	font-size: var(--text-sm);
	color: var(--text-muted);
	margin-top: 2px;
}

.doc-detail__header-actions {
	display: flex;
	align-items: center;
	gap: 12px;
	flex: 0 0 auto;
}

.doc-detail__close {
	appearance: none;
	border: none;
	background: none;
	font-size: 22px;
	line-height: 1;
	color: var(--text-muted);
	cursor: pointer;
	padding: 2px 4px;
}

.doc-detail__close:hover {
	color: var(--text-color);
}

.doc-detail__body {
	flex: 1 1 auto;
	overflow-y: auto;
	padding: 18px;
	display: flex;
	flex-direction: column;
	gap: 22px;
}

.doc-detail__section-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 10px;
}

.doc-detail__section-title {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
	margin-bottom: 10px;
}

.doc-detail__section-head .doc-detail__section-title {
	margin-bottom: 0;
}

.doc-detail__status-row {
	display: flex;
	gap: 8px;
	margin-bottom: 12px;
}

.doc-detail__meta {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 10px 16px;
	margin: 0;
}

.doc-detail__meta dt {
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.doc-detail__meta dd {
	margin: 2px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
}

.doc-detail__description {
	margin-top: 12px;
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: pre-wrap;
}

.doc-detail__meta--drawing {
	margin-top: 12px;
	padding-top: 12px;
	border-top: 1px dashed var(--border-color);
}

.doc-detail__readiness-select {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	color: var(--text-color);
	padding: 3px 6px;
	font-size: var(--text-xs);
}

.doc-detail__file {
	margin-top: 12px;
	font-size: var(--text-sm);
	display: flex;
	align-items: center;
	gap: 10px;
}

.doc-detail__open-link {
	margin-left: -2px;
}

.doc-detail__preview-cell {
	padding: 10px 0 !important;
}

.doc-detail__meta-label {
	color: var(--text-muted);
	margin-right: 6px;
}

.doc-detail__current-badge {
	margin-left: 6px;
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--dark-green-500, var(--green-500));
}

.doc-detail__list {
	list-style: none;
	margin: 0;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.doc-detail__list li {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 10px;
	padding: 8px 10px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	font-size: var(--text-sm);
}

.hub-link {
	color: var(--text-color);
	cursor: pointer;
	text-decoration: none;
	border-bottom: 1px dashed var(--border-color);
}

.hub-link:hover {
	color: var(--text-color);
	border-bottom-color: var(--text-color);
}

.doc-detail__section-head-actions {
	display: flex;
	gap: 8px;
	flex: 0 0 auto;
}

.doc-detail__compare-hint {
	margin: 0 0 10px;
	font-size: var(--text-xs);
	color: var(--text-muted);
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

@media (max-width: 640px) {
	.doc-detail__panel {
		width: 100vw;
	}

	.doc-detail__meta {
		grid-template-columns: 1fr;
	}
}
</style>
