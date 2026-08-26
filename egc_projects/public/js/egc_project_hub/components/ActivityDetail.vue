<!-- Activity detail workspace (docs/ARCHITECTURE_V2.md §5/§6/§8) — the Hub-native replacement
     for dropping straight into the native EGC Activity form on every row click. Same right-hand
     drawer shell as DocumentDetail.vue (doc-detail__* renamed activity-detail__*), same "Open
     Form" escape hatch for power users, same LoadingState/ErrorState/EmptyState conventions.

     A group Activity's schedule/progress fields are rollup-owned by activity_control.py — this
     view renders them read-only with a small "derived from children" note rather than pretend
     they are editable, matching the DocType's own read_only_depends_on rule. -->
<script setup>
import { ref, watch } from "vue";
import {
	get_activity_detail,
	add_dependency,
	remove_dependency,
	update_activity_progress,
	create_activity,
	update_activity_fields,
} from "./activities_api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";
import ActivityLinkedRecords from "./ActivityLinkedRecords.vue";

const props = defineProps({
	activity: { type: String, required: true },
	project: { type: String, required: true },
	canWrite: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "changed", "open-activity"]);

const { data, loading, error, reload } = useHubResource(() => get_activity_detail(props.activity));
watch(() => props.activity, reload, { immediate: true });

function notify_changed() {
	emit("changed");
	reload();
}

function open_form() {
	frappe.set_route("Form", "EGC Activity", props.activity);
}

// Deliberately a small, fixed field set here (not a generic form builder) — dates, discipline,
// WBS and responsible party cover the routine "fix a typo / reassign / reschedule" edit without
// reimplementing the native form. Schedule fields on a group are excluded outright since they
// are rollup-owned; "Open Form" remains the escape hatch for anything not covered here.
function open_edit_dialog() {
	const activity = data.value.activity;
	const fields = [
		{ fieldname: "activity_name", fieldtype: "Data", label: __("Activity Name"), default: activity.activity_name, reqd: 1 },
		{ fieldname: "wbs_node", fieldtype: "Link", label: __("WBS Node"), options: "EGC WBS Node", default: activity.wbs_node, get_query: () => ({ filters: { project: props.project } }) },
		{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline", default: activity.discipline },
		{ fieldname: "responsible_user", fieldtype: "Link", label: __("Responsible User"), options: "User", default: activity.responsible_user },
		{ fieldname: "responsible_supplier", fieldtype: "Link", label: __("Responsible Supplier"), options: "Supplier", default: activity.responsible_supplier },
	];
	if (!activity.is_group) {
		fields.push(
			{ fieldname: "planned_start_date", fieldtype: "Date", label: __("Planned Start"), default: activity.planned_start_date },
			{ fieldname: "planned_end_date", fieldtype: "Date", label: __("Planned Finish"), default: activity.planned_end_date },
			{ fieldname: "forecast_start_date", fieldtype: "Date", label: __("Forecast Start"), default: activity.forecast_start_date },
			{ fieldname: "forecast_end_date", fieldtype: "Date", label: __("Forecast Finish"), default: activity.forecast_end_date },
			{ fieldname: "actual_start_date", fieldtype: "Date", label: __("Actual Start"), default: activity.actual_start_date },
			{ fieldname: "actual_end_date", fieldtype: "Date", label: __("Actual Finish"), default: activity.actual_end_date },
			{ fieldname: "is_milestone", fieldtype: "Check", label: __("Is Milestone"), default: activity.is_milestone }
		);
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Edit Activity"),
		fields,
		primary_action_label: __("Save"),
		primary_action(values) {
			update_activity_fields(props.activity, values)
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

function open_activity(name) {
	// Re-targets this SAME drawer at a related activity (a dependency or a child row) instead of
	// stacking a second one, or leaving the Hub outright — matches "navigate to related records"
	// from §8. ActivitiesTab.vue owns `selected_activity` and updates it on this event; the
	// drawer's own `watch(() => props.activity, reload)` then reloads in place.
	emit("open-activity", name);
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

// duration_days is an Int field with no nullable representation in Frappe (see
// activity_control.py) — 0 is the documented "not computed" sentinel, never a real duration.
function format_duration(value) {
	return value ? __("{0} days", [value]) : "—";
}

const document_links = () => (data.value?.links || []).filter((row) => row.link_doctype === "EGC Project Document");
const submittal_links = () => (data.value?.links || []).filter((row) => row.link_doctype === "EGC Submittal");

// -- inline progress update ------------------------------------------------------------------

const editing_progress = ref(false);
const progress_draft = ref(0);
const status_draft = ref("");
const saving_progress = ref(false);
const STATUS_OPTIONS = ["Not Started", "In Progress", "On Hold", "Completed", "Cancelled"];

function start_progress_edit() {
	progress_draft.value = data.value.activity.percent_complete || 0;
	status_draft.value = data.value.activity.status;
	editing_progress.value = true;
}

async function save_progress() {
	saving_progress.value = true;
	try {
		await update_activity_progress(props.activity, progress_draft.value, status_draft.value);
		editing_progress.value = false;
		notify_changed();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Update Progress"), message: e.message, indicator: "red" });
	} finally {
		saving_progress.value = false;
	}
}

// -- add child ---------------------------------------------------------------------------------

function open_add_child_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Child Activity"),
		fields: [
			{ fieldname: "activity_code", fieldtype: "Data", label: __("Activity Code"), reqd: 1 },
			{ fieldname: "activity_name", fieldtype: "Data", label: __("Activity Name"), reqd: 1 },
			{ fieldname: "is_group", fieldtype: "Check", label: __("Is Group") },
			{
				fieldname: "wbs_node",
				fieldtype: "Link",
				label: __("WBS Node"),
				options: "EGC WBS Node",
				default: data.value?.activity?.wbs_node,
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "discipline",
				fieldtype: "Link",
				label: __("Discipline"),
				options: "EGC Discipline",
				default: data.value?.activity?.discipline,
			},
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			create_activity({ ...values, project: props.project, parent_egc_activity: props.activity })
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Create Activity"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

// -- dependencies --------------------------------------------------------------------------------

const DEPENDENCY_TYPES = ["Finish-to-Start", "Start-to-Start", "Finish-to-Finish", "Start-to-Finish"];

function open_add_dependency_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Dependency"),
		fields: [
			{
				fieldname: "direction",
				fieldtype: "Select",
				label: __("Direction"),
				options: [__("This activity depends on…"), __("…depends on this activity")],
				default: __("This activity depends on…"),
				reqd: 1,
			},
			{
				fieldname: "other_activity",
				fieldtype: "Link",
				label: __("Activity"),
				options: "EGC Activity",
				reqd: 1,
				get_query: () => ({ filters: { project: props.project, name: ["!=", props.activity] } }),
			},
			{
				fieldname: "dependency_type",
				fieldtype: "Select",
				label: __("Type"),
				options: DEPENDENCY_TYPES,
				default: "Finish-to-Start",
			},
			{ fieldname: "lag_days", fieldtype: "Int", label: __("Lag (Days)"), default: 0 },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			const forward = values.direction === __("This activity depends on…");
			const predecessor = forward ? values.other_activity : props.activity;
			const successor = forward ? props.activity : values.other_activity;
			add_dependency(predecessor, successor, values.dependency_type, values.lag_days)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Dependency"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_remove_dependency(name) {
	frappe.confirm(__("Remove this dependency?"), () => {
		remove_dependency(name)
			.then(notify_changed)
			.catch((e) => {
				frappe.msgprint({ title: __("Could Not Remove Dependency"), message: e.message, indicator: "red" });
			});
	});
}
</script>

<template>
	<div class="activity-detail__backdrop" @click.self="$emit('close')">
		<div class="activity-detail__panel" role="dialog" aria-modal="true">
			<div class="activity-detail__header">
				<div class="activity-detail__identity">
					<div class="activity-detail__code">{{ data?.activity?.activity_code || activity }}</div>
					<div class="activity-detail__name">{{ data?.activity?.activity_name || "" }}</div>
				</div>
				<div class="activity-detail__header-actions">
					<a v-if="canWrite && data" href="#" class="hub-link" @click.prevent="open_edit_dialog">{{ __("Edit") }}</a>
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
							<StatusPill :status="data.activity.status" />
							<span v-if="data.activity.is_milestone" class="indicator-pill blue">{{ __("Milestone") }}</span>
							<span v-if="data.activity.is_group" class="indicator-pill gray">{{ __("Group") }}</span>
						</div>

						<div class="activity-detail__progress-row">
							<div class="hub-percent">
								<div class="hub-percent__track">
									<div
										class="hub-percent__fill"
										:style="{ width: (data.activity.percent_complete || 0) + '%' }"
									/>
								</div>
								<span class="hub-percent__value">{{ Math.round(data.activity.percent_complete || 0) }}%</span>
							</div>
							<button
								v-if="canWrite && !data.activity.is_group && !editing_progress"
								type="button"
								class="btn btn-xs btn-default"
								@click="start_progress_edit"
							>
								{{ __("Update Progress") }}
							</button>
							<span v-else-if="data.activity.is_group" class="activity-detail__derived-note">
								{{ __("Derived from children") }}
							</span>
						</div>

						<div v-if="editing_progress" class="activity-detail__progress-edit">
							<input v-model.number="progress_draft" type="number" min="0" max="100" step="1" />
							<select v-model="status_draft">
								<option v-for="s in STATUS_OPTIONS" :key="s" :value="s">{{ s }}</option>
							</select>
							<button type="button" class="btn btn-xs btn-primary" :disabled="saving_progress" @click="save_progress">
								{{ __("Save") }}
							</button>
							<button type="button" class="btn btn-xs btn-default" @click="editing_progress = false">
								{{ __("Cancel") }}
							</button>
						</div>

						<dl class="activity-detail__meta">
							<div>
								<dt>{{ __("WBS") }}</dt>
								<dd>{{ data.activity.wbs_node || "—" }}</dd>
							</div>
							<div>
								<dt>{{ __("Discipline") }}</dt>
								<dd>{{ data.activity.discipline || "—" }}</dd>
							</div>
							<div>
								<dt>{{ __("Responsible") }}</dt>
								<dd>{{ data.activity.responsible_user || data.activity.responsible_supplier || "—" }}</dd>
							</div>
						</dl>
					</section>

					<section class="activity-detail__section">
						<div class="activity-detail__section-title">{{ __("Schedule") }}</div>
						<dl class="activity-detail__meta">
							<div>
								<dt>{{ __("Planned Start") }}</dt>
								<dd>{{ format_date(data.activity.planned_start_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Planned Finish") }}</dt>
								<dd>{{ format_date(data.activity.planned_end_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Duration") }}</dt>
								<dd>{{ format_duration(data.activity.duration_days) }}</dd>
							</div>
							<div>
								<dt>{{ __("Actual Start") }}</dt>
								<dd>{{ format_date(data.activity.actual_start_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Actual Finish") }}</dt>
								<dd>{{ format_date(data.activity.actual_end_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Forecast Start") }}</dt>
								<dd>{{ format_date(data.activity.forecast_start_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Forecast Finish") }}</dt>
								<dd>{{ format_date(data.activity.forecast_end_date) }}</dd>
							</div>
						</dl>
						<p v-if="data.activity.is_group" class="activity-detail__derived-note">
							{{ __("Schedule fields on a group are derived from its children and cannot be edited directly.") }}
						</p>
					</section>

					<section class="activity-detail__section">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Dependencies") }}</div>
							<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_add_dependency_dialog">
								{{ __("Add Dependency") }}
							</button>
						</div>
						<div class="activity-detail__dep-group">
							<div class="activity-detail__dep-label">{{ __("Predecessors") }}</div>
							<EmptyState v-if="!data.dependencies.predecessors.length" :title="__('None')" />
							<ul v-else class="activity-detail__list">
								<li v-for="dep in data.dependencies.predecessors" :key="dep.name">
									<a href="#" class="activity-detail__link" @click.prevent="open_activity(dep.activity)">
										{{ dep.activity_code }}: {{ dep.activity_name }}
									</a>
									<div class="activity-links__meta">
										<StatusPill :status="dep.status" />
										<span class="activity-detail__dep-type">{{ dep.dependency_type }}<template v-if="dep.lag_days"> · {{ __("Lag") }} {{ dep.lag_days }}d</template></span>
										<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="confirm_remove_dependency(dep.name)">
											{{ __("Remove") }}
										</button>
									</div>
								</li>
							</ul>
						</div>
						<div class="activity-detail__dep-group">
							<div class="activity-detail__dep-label">{{ __("Successors") }}</div>
							<EmptyState v-if="!data.dependencies.successors.length" :title="__('None')" />
							<ul v-else class="activity-detail__list">
								<li v-for="dep in data.dependencies.successors" :key="dep.name">
									<a href="#" class="activity-detail__link" @click.prevent="open_activity(dep.activity)">
										{{ dep.activity_code }}: {{ dep.activity_name }}
									</a>
									<div class="activity-links__meta">
										<StatusPill :status="dep.status" />
										<span class="activity-detail__dep-type">{{ dep.dependency_type }}<template v-if="dep.lag_days"> · {{ __("Lag") }} {{ dep.lag_days }}d</template></span>
										<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="confirm_remove_dependency(dep.name)">
											{{ __("Remove") }}
										</button>
									</div>
								</li>
							</ul>
						</div>
					</section>

					<section v-if="data.activity.is_group" class="activity-detail__section">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Children") }}</div>
							<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_add_child_dialog">
								{{ __("Add Child Activity") }}
							</button>
						</div>
						<EmptyState v-if="!data.children.length" :title="__('No child activities yet')" />
						<ul v-else class="activity-detail__list">
							<li v-for="child in data.children" :key="child.name">
								<a href="#" class="activity-detail__link" @click.prevent="open_activity(child.name)">
									{{ child.activity_code }}: {{ child.activity_name }}
									<span v-if="child.is_milestone" class="activity-detail__milestone-dot" :title="__('Milestone')" />
								</a>
								<div class="activity-links__meta">
									<StatusPill :status="child.status" />
									<span class="activity-detail__dep-type">{{ Math.round(child.percent_complete || 0) }}%</span>
								</div>
							</li>
						</ul>
					</section>

					<section v-else class="activity-detail__section">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Children") }}</div>
							<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_add_child_dialog">
								{{ __("Add Child Activity") }}
							</button>
						</div>
						<p class="activity-detail__derived-note">
							{{ __("Adding a child will make this a group activity — its schedule and progress will then be derived from its children.") }}
						</p>
					</section>

					<section class="activity-detail__section">
						<ActivityLinkedRecords
							:activity="activity"
							:project="project"
							link-doctype="EGC Submittal"
							:title="__('Submittals')"
							:empty-message="__('No linked submittals yet')"
							:rows="submittal_links()"
							:can-write="canWrite"
							@changed="notify_changed"
						/>
					</section>

					<section class="activity-detail__section">
						<ActivityLinkedRecords
							:activity="activity"
							:project="project"
							link-doctype="EGC Project Document"
							:title="__('Drawings & Documents')"
							:empty-message="__('No linked documents yet')"
							:rows="document_links()"
							:can-write="canWrite"
							@changed="notify_changed"
						/>
					</section>

					<section class="activity-detail__section">
						<div class="activity-detail__section-title">{{ __("History") }}</div>
						<dl class="activity-detail__meta">
							<div>
								<dt>{{ __("Created") }}</dt>
								<dd>{{ format_date(data.activity.creation) }}</dd>
							</div>
							<div>
								<dt>{{ __("Last Modified") }}</dt>
								<dd>{{ format_date(data.activity.modified) }}</dd>
							</div>
						</dl>
					</section>
				</template>
			</div>
		</div>
	</div>
</template>

<style scoped>
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

.activity-detail__progress-row {
	display: flex;
	align-items: center;
	gap: 12px;
	margin-bottom: 8px;
}

.activity-detail__progress-edit {
	display: flex;
	align-items: center;
	gap: 8px;
	margin-bottom: 12px;
}

.activity-detail__progress-edit input[type="number"] {
	width: 70px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	color: var(--text-color);
	padding: 4px 8px;
}

.activity-detail__progress-edit select {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	color: var(--text-color);
	padding: 4px 8px;
}

.activity-detail__derived-note {
	font-size: var(--text-xs);
	color: var(--text-muted);
	font-style: italic;
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

.activity-detail__dep-group {
	margin-bottom: 14px;
}

.activity-detail__dep-group:last-child {
	margin-bottom: 0;
}

.activity-detail__dep-label {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
	margin-bottom: 6px;
}

.activity-detail__dep-type {
	font-size: var(--text-xs);
	color: var(--text-muted);
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

.activity-detail__milestone-dot {
	display: inline-block;
	width: 8px;
	height: 8px;
	margin-left: 6px;
	transform: rotate(45deg);
	background: var(--blue-500, var(--text-color));
	vertical-align: middle;
}

.activity-links__meta {
	display: flex;
	align-items: center;
	gap: 8px;
	flex: 0 0 auto;
}

.hub-percent {
	display: flex;
	align-items: center;
	gap: 8px;
	min-width: 110px;
}

.hub-percent__track {
	flex: 1;
	height: 6px;
	border-radius: var(--border-radius-full);
	background: var(--control-bg);
	overflow: hidden;
}

.hub-percent__fill {
	height: 100%;
	background: var(--dark-green-500, var(--green-500));
}

.hub-percent__value {
	font-size: var(--text-xs);
	color: var(--text-muted);
	width: 32px;
	text-align: right;
}
</style>
