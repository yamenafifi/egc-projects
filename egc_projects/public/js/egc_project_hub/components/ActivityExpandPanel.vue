<!-- Inline "drop down and showcase what's underneath" panel for one Activities-table row
     (Procore-style: the linked Submittals/Documents/Dependencies for an Activity are visible
     without navigating away from the list — ActivityDetail.vue's drawer remains the place to
     actually edit an Activity, reached via the "Open" link this panel exposes).

     Reuses get_activity_detail (the same call ActivityDetail.vue makes) and
     ActivityLinkedRecords.vue (the same list it already renders per link_doctype) — this is
     purely a different, inline shell around data the app already fetches and displays. A small
     "tools" strip (mirroring Procore's own per-record tool switcher) lets a Project Manager flip
     between what's underneath an Activity without the panel growing to show everything stacked
     at once; each tool's badge count is available immediately from `linkCounts` (already fetched
     for the whole table in one query — see api/hub.py's get_activities), before the per-Activity
     detail round trip even resolves. -->
<script setup>
import { computed, ref, watch } from "vue";
import { get_activity_detail, link_activity_record, unlink_activity_record } from "./activities_api";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps({
	activity: { type: String, required: true },
	project: { type: String, required: true },
	canWrite: { type: Boolean, default: false },
	linkCounts: { type: Object, default: () => ({}) },
});
const emit = defineEmits(["open-detail", "changed"]);

const data = ref(null);
const loading = ref(true);
const error = ref(null);

async function load() {
	loading.value = true;
	error.value = null;
	try {
		data.value = await get_activity_detail(props.activity);
	} catch (e) {
		error.value = e.message;
	} finally {
		loading.value = false;
	}
}

watch(() => props.activity, load, { immediate: true });

function reload() {
	load();
	emit("changed");
}

const submittal_links = computed(() => (data.value?.links || []).filter((row) => row.link_doctype === "EGC Submittal"));
const document_links = computed(() =>
	(data.value?.links || []).filter((row) => row.link_doctype === "EGC Project Document")
);
const dependencies = computed(() => data.value?.dependencies || { predecessors: [], successors: [] });
const dependency_count = computed(() => dependencies.value.predecessors.length + dependencies.value.successors.length);

// Badge counts are immediately available from the table's own batched query (props.linkCounts),
// so the strip renders real numbers before the per-Activity round trip above resolves; once it
// does, the actual filtered arrays take over (a link added/removed via this panel is reflected
// without waiting on the parent table's own next reload).
const submittal_count = computed(() =>
	data.value ? submittal_links.value.length : props.linkCounts["EGC Submittal"] || 0
);
const document_count = computed(() =>
	data.value ? document_links.value.length : props.linkCounts["EGC Project Document"] || 0
);

const TOOLS = [
	{ key: "submittals", label: __("Submittals") },
	{ key: "documents", label: __("Drawings & Documents") },
	{ key: "dependencies", label: __("Dependencies") },
];

// Opens on whichever tool actually has something to show — the most useful view first, matching
// what a Project Manager scanning the list is most likely looking for.
const active_tool = ref(
	props.linkCounts["EGC Submittal"]
		? "submittals"
		: props.linkCounts["EGC Project Document"]
			? "documents"
			: "submittals"
);

function tool_count(key) {
	if (key === "submittals") return submittal_count.value;
	if (key === "documents") return document_count.value;
	return dependency_count.value;
}

function open_activity(name) {
	emit("open-detail", name);
}

// -- submittals table (row.* fields come from relationships._TARGET_STATUS_FIELDS["EGC
// Submittal"] — the same fields the main Submittals register itself shows) --------------------

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

// Mirrors api/hub.py's get_submittals() is_overdue rule exactly (current_due_date in the past,
// status still one of the two "open" ones) — relationships.py is a generic linking module and
// deliberately doesn't know submittal-specific status semantics, so this is computed here
// instead of being a field the backend already sends.
const SUBMISSION_OPEN_STATUSES = ["Submitted", "Under Review"];
function is_submittal_overdue(row) {
	if (!row.current_due_date) return false;
	if (!SUBMISSION_OPEN_STATUSES.includes(row.submittal_status)) return false;
	return frappe.datetime.get_diff(row.current_due_date, frappe.datetime.get_today()) < 0;
}

function open_submittal(row) {
	frappe.set_route("Form", "EGC Submittal", row.link_name);
}

function open_add_submittal_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Link Submittal"),
		fields: [
			{
				fieldname: "link_name",
				fieldtype: "Link",
				label: __("Submittal"),
				options: "EGC Submittal",
				reqd: 1,
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "link_purpose",
				fieldtype: "Select",
				label: __("Purpose"),
				options: ["Reference", "Requirement"],
				default: "Reference",
			},
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			link_activity_record(props.activity, "EGC Submittal", values.link_name, values.link_purpose, values.remarks)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Link"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_remove_submittal(row) {
	frappe.confirm(__("Remove this link?"), () => {
		unlink_activity_record(row.name)
			.then(reload)
			.catch((e) => {
				frappe.msgprint({ title: __("Could Not Remove Link"), message: e.message, indicator: "red" });
			});
	});
}

// -- documents table (row.* fields come from relationships._TARGET_STATUS_FIELDS["EGC Project
// Document"] — the same fields DocumentsTab.vue's own register shows) ---------------------------

function open_document(row) {
	frappe.set_route("Form", "EGC Project Document", row.link_name);
}

function open_add_document_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Link Document"),
		fields: [
			{
				fieldname: "link_name",
				fieldtype: "Link",
				label: __("Document"),
				options: "EGC Project Document",
				reqd: 1,
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "link_purpose",
				fieldtype: "Select",
				label: __("Purpose"),
				options: ["Reference", "Requirement"],
				default: "Reference",
			},
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			link_activity_record(props.activity, "EGC Project Document", values.link_name, values.link_purpose, values.remarks)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Link"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_remove_document(row) {
	frappe.confirm(__("Remove this link?"), () => {
		unlink_activity_record(row.name)
			.then(reload)
			.catch((e) => {
				frappe.msgprint({ title: __("Could Not Remove Link"), message: e.message, indicator: "red" });
			});
	});
}
</script>

<template>
	<div class="activity-expand">
		<LoadingState v-if="loading" :rows="2" />
		<ErrorState v-else-if="error" :message="error" @retry="load" />

		<template v-else-if="data">
			<div class="activity-expand__tools">
				<button
					v-for="tool in TOOLS"
					:key="tool.key"
					type="button"
					class="activity-expand__tool"
					:class="{ 'activity-expand__tool--active': active_tool === tool.key }"
					@click="active_tool = tool.key"
				>
					{{ tool.label }}
					<span class="activity-expand__badge">{{ tool_count(tool.key) }}</span>
				</button>
				<a href="#" class="hub-link activity-expand__open" @click.prevent="open_activity(activity)">
					{{ __("Open full detail") }}
				</a>
			</div>

			<div class="activity-expand__body">
				<div v-if="active_tool === 'submittals'" class="activity-expand__submittals">
					<div class="activity-expand__table-head">
						<div class="activity-detail__section-title">{{ __("Submittals") }}</div>
						<button
							v-if="canWrite && !data.activity.is_group"
							type="button"
							class="btn btn-xs btn-default"
							@click="open_add_submittal_dialog"
						>
							{{ __("Link Existing") }}
						</button>
					</div>
					<EmptyState
						v-if="!submittal_links.length"
						:title="data.activity.is_group ? __('Not applicable to a Group Activity') : __('No linked submittals yet')"
					/>
					<div v-else class="hub-table-wrap">
						<table class="hub-table">
							<thead>
								<tr>
									<th>{{ __("Submittal No") }}</th>
									<th>{{ __("Title") }}</th>
									<th>{{ __("Type") }}</th>
									<th>{{ __("Discipline") }}</th>
									<th>{{ __("Current Submission") }}</th>
									<th>{{ __("Status") }}</th>
									<th>{{ __("Ball in Court") }}</th>
									<th>{{ __("Due Date") }}</th>
									<th>{{ __("Purpose") }}</th>
									<th v-if="canWrite"></th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="row in submittal_links"
									:key="row.name"
									class="hub-table__row--clickable"
									@click="open_submittal(row)"
								>
									<td>{{ row.submittal_number || "—" }}</td>
									<td class="hub-table__truncate" :title="row.link_title">{{ row.link_title || "—" }}</td>
									<td>{{ row.submittal_type || "—" }}</td>
									<td>{{ row.discipline || "—" }}</td>
									<td>{{ row.current_submission_label || "—" }}</td>
									<td><StatusPill :status="row.submittal_status" /></td>
									<td>{{ row.ball_in_court || "—" }}</td>
									<td :class="{ 'hub-table__overdue': is_submittal_overdue(row) }">
										{{ format_date(row.current_due_date) }}
										<span v-if="is_submittal_overdue(row)" class="hub-table__overdue-tag">{{ __("Overdue") }}</span>
									</td>
									<td>{{ row.link_purpose || "—" }}</td>
									<td v-if="canWrite">
										<button
											type="button"
											class="btn btn-xs btn-default"
											@click.stop="confirm_remove_submittal(row)"
										>
											{{ __("Remove") }}
										</button>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>

				<div v-else-if="active_tool === 'documents'" class="activity-expand__submittals">
					<div class="activity-expand__table-head">
						<div class="activity-detail__section-title">{{ __("Drawings & Documents") }}</div>
						<button
							v-if="canWrite && !data.activity.is_group"
							type="button"
							class="btn btn-xs btn-default"
							@click="open_add_document_dialog"
						>
							{{ __("Link Existing") }}
						</button>
					</div>
					<EmptyState
						v-if="!document_links.length"
						:title="data.activity.is_group ? __('Not applicable to a Group Activity') : __('No linked documents yet')"
					/>
					<div v-else class="hub-table-wrap">
						<table class="hub-table">
							<thead>
								<tr>
									<th>{{ __("Document No") }}</th>
									<th>{{ __("Title") }}</th>
									<th>{{ __("Discipline") }}</th>
									<th>{{ __("Current Revision") }}</th>
									<th>{{ __("Status") }}</th>
									<th>{{ __("Purpose") }}</th>
									<th v-if="canWrite"></th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="row in document_links"
									:key="row.name"
									class="hub-table__row--clickable"
									@click="open_document(row)"
								>
									<td>{{ row.document_number || "—" }}</td>
									<td class="hub-table__truncate" :title="row.link_title">{{ row.link_title || "—" }}</td>
									<td>{{ row.discipline || "—" }}</td>
									<td>{{ row.current_revision_label || "—" }}</td>
									<td><StatusPill :status="row.approval_status" /></td>
									<td>{{ row.link_purpose || "—" }}</td>
									<td v-if="canWrite">
										<button
											type="button"
											class="btn btn-xs btn-default"
											@click.stop="confirm_remove_document(row)"
										>
											{{ __("Remove") }}
										</button>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>

				<div v-else class="activity-expand__deps">
					<div class="activity-expand__dep-group">
						<div class="activity-expand__dep-label">{{ __("Predecessors") }}</div>
						<EmptyState v-if="!dependencies.predecessors.length" :title="__('None')" />
						<ul v-else class="activity-detail__list">
							<li v-for="dep in dependencies.predecessors" :key="dep.name">
								<a href="#" class="activity-detail__link" @click.prevent="open_activity(dep.activity)">
									{{ dep.activity_code }}: {{ dep.activity_name }}
								</a>
								<div class="activity-links__meta">
									<StatusPill :status="dep.status" />
									<span class="activity-detail__dep-type">{{ dep.dependency_type }}</span>
								</div>
							</li>
						</ul>
					</div>
					<div class="activity-expand__dep-group">
						<div class="activity-expand__dep-label">{{ __("Successors") }}</div>
						<EmptyState v-if="!dependencies.successors.length" :title="__('None')" />
						<ul v-else class="activity-detail__list">
							<li v-for="dep in dependencies.successors" :key="dep.name">
								<a href="#" class="activity-detail__link" @click.prevent="open_activity(dep.activity)">
									{{ dep.activity_code }}: {{ dep.activity_name }}
								</a>
								<div class="activity-links__meta">
									<StatusPill :status="dep.status" />
									<span class="activity-detail__dep-type">{{ dep.dependency_type }}</span>
								</div>
							</li>
						</ul>
					</div>
				</div>
			</div>
		</template>
	</div>
</template>

<style scoped>
.activity-expand {
	padding: 14px 18px 18px 46px;
	background: var(--subtle-fg, var(--control-bg));
	border-top: 1px solid var(--border-color);
	border-bottom: 1px solid var(--border-color);
}

.activity-expand__tools {
	display: flex;
	align-items: center;
	gap: 4px;
	margin-bottom: 12px;
	border-bottom: 1px solid var(--border-color);
}

.activity-expand__tool {
	appearance: none;
	border: none;
	background: none;
	padding: 8px 12px;
	font-size: var(--text-sm);
	color: var(--text-muted);
	cursor: pointer;
	border-bottom: 2px solid transparent;
	margin-bottom: -1px;
	display: flex;
	align-items: center;
	gap: 6px;
}

.activity-expand__tool:hover {
	color: var(--text-color);
}

.activity-expand__tool--active {
	color: var(--text-color);
	font-weight: 600;
	border-bottom-color: var(--dark-green-500, var(--green-500));
}

.activity-expand__badge {
	font-size: var(--text-xs);
	color: var(--text-muted);
	background: var(--control-bg);
	border-radius: var(--border-radius-full);
	padding: 0 6px;
	min-width: 18px;
	text-align: center;
}

.activity-expand__tool--active .activity-expand__badge {
	background: var(--fg-color);
}

.activity-expand__open {
	margin-left: auto;
	font-size: var(--text-xs);
	white-space: nowrap;
	padding: 0 4px 8px;
}

.activity-expand__deps {
	display: flex;
	flex-direction: column;
	gap: 14px;
}

.activity-expand__dep-label {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
	margin-bottom: 6px;
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
	background: var(--fg-color);
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

.activity-detail__section-title {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
}

.activity-expand__table-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 10px;
}
</style>
