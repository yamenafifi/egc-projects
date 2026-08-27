<script setup>
import { computed, ref, watch, onMounted } from "vue";
import { get_activities } from "../api";
import { create_activity as create_activity_record } from "./activities_api";
import { useHubResource } from "../composables/useHubResource";
import { consumeOverdueIntent } from "../composables/useOverdueIntent";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";
import ActivityDetail from "./ActivityDetail.vue";
import ActivityExpandPanel from "./ActivityExpandPanel.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { data, loading, error, reload } = useHubResource(() => get_activities(props.project));
watch(() => props.project, reload, { immediate: true });

// A client-side hint only, same discipline as every write action elsewhere in this Hub — the
// server's own permission checks (validators.require_project_permission +
// frappe.has_permission in api/activities.py) are the actual boundary; this just avoids
// showing a button a Viewer would immediately get rejected for.
const WRITE_ROLES = ["EGC Project Manager", "EGC Project Engineer", "System Manager"];
const can_write = computed(() => (frappe.user_roles || []).some((role) => WRITE_ROLES.includes(role)));

const selected_activity = ref(null);

function open_detail(name) {
	selected_activity.value = name;
}

function close_detail() {
	selected_activity.value = null;
}

function on_detail_changed() {
	reload();
}

// -- inline expand: "drop down and showcase what's underneath" without navigating away ---------

const expanded = ref(new Set());

function toggle_expand(name) {
	const next = new Set(expanded.value);
	if (next.has(name)) {
		next.delete(name);
	} else {
		next.add(name);
	}
	expanded.value = next;
}

// Toggle column + Code/Name/WBS/Discipline/Planned Start/Planned Finish/Duration/Actual
// Finish/Status/Weight/% Complete/Responsible, plus the actions column when it's shown.
const column_count = computed(() => 13 + (can_write.value ? 1 : 0));

const status_filter = ref("");
const discipline_filter = ref("");
const overdue_only = ref(false);
const search = ref("");

onMounted(() => {
	if (consumeOverdueIntent("activities")) overdue_only.value = true;
});

const statuses = computed(() => [...new Set((data.value || []).map((r) => r.status).filter(Boolean))].sort());
const disciplines = computed(() =>
	[...new Set((data.value || []).map((r) => r.discipline).filter(Boolean))].sort()
);

const filtered = computed(() => {
	const term = search.value.trim().toLowerCase();
	return (data.value || []).filter((row) => {
		if (status_filter.value && row.status !== status_filter.value) return false;
		if (discipline_filter.value && row.discipline !== discipline_filter.value) return false;
		if (overdue_only.value && !row.is_overdue) return false;
		if (term && !`${row.activity_code} ${row.activity_name}`.toLowerCase().includes(term)) return false;
		return true;
	});
});

function create_activity() {
	// Empty-state action for a project with no activities at all yet — a bare top-level
	// creation still goes to the native "New" form (there is no sensible quick-add target
	// without an existing group to attach to). Once at least one activity exists, the
	// per-row "+" quick-add and the detail drawer's "Add Child Activity" cover routine growth
	// of the tree without leaving the Hub.
	frappe.new_doc("EGC Activity", { project: props.project });
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

// duration_days is an Int field with no nullable representation in Frappe (see
// activity_control.py) — 0 is the documented "not computed" sentinel, never a real duration.
function format_duration(value) {
	return value ? __("{0}d", [value]) : "—";
}

// weight_pct defaults to 0 (see egc_activity.json) for an Activity that hasn't been allocated a
// share yet — indistinguishable from a genuine 0% allocation, so both render as "not set" here,
// matching duration_days's own 0-as-sentinel convention above.
function format_weight(value) {
	return value ? __("{0}%", [Math.round(value)]) : "—";
}

function open_quick_add(row) {
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
				default: row.wbs_node,
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "discipline",
				fieldtype: "Link",
				label: __("Discipline"),
				options: "EGC Discipline",
				default: row.discipline,
			},
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			create_activity_record({ ...values, project: props.project, parent_egc_activity: row.name })
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Create Activity"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}
</script>

<template>
	<div class="hub-activities">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />
		<EmptyState
			v-else-if="!(data || []).length"
			:title="__('No activities yet')"
			:description="__('Activities describe the execution breakdown of this project.')"
			:action-label="__('New Activity')"
			@action="create_activity"
		/>

		<template v-else>
			<div class="hub-toolbar">
				<input v-model="search" type="text" :placeholder="__('Search code or name…')" />
				<select v-model="status_filter">
					<option value="">{{ __("All Statuses") }}</option>
					<option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
				</select>
				<select v-model="discipline_filter">
					<option value="">{{ __("All Disciplines") }}</option>
					<option v-for="d in disciplines" :key="d" :value="d">{{ d }}</option>
				</select>
				<label class="hub-toolbar__check">
					<input v-model="overdue_only" type="checkbox" />
					{{ __("Overdue only") }}
				</label>
			</div>

			<EmptyState v-if="!filtered.length" :title="__('No activities match these filters')" />
			<div v-else class="hub-table-wrap">
				<table class="hub-table">
					<thead>
						<tr>
							<th class="hub-activities__toggle-col"></th>
							<th>{{ __("Code") }}</th>
							<th>{{ __("Name") }}</th>
							<th>{{ __("WBS") }}</th>
							<th>{{ __("Discipline") }}</th>
							<th>{{ __("Planned Start") }}</th>
							<th>{{ __("Planned Finish") }}</th>
							<th>{{ __("Duration") }}</th>
							<th>{{ __("Actual Finish") }}</th>
							<th>{{ __("Status") }}</th>
							<th :title="__('Share of parent\'s rolled-up progress')">{{ __("Weight") }}</th>
							<th>{{ __("% Complete") }}</th>
							<th>{{ __("Responsible") }}</th>
							<th v-if="can_write"></th>
						</tr>
					</thead>
					<tbody>
						<template v-for="row in filtered" :key="row.name">
							<tr class="hub-table__row--clickable" @click="toggle_expand(row.name)">
								<td class="hub-activities__toggle-col">
									<button
										type="button"
										class="hub-activities__toggle"
										:class="{ 'hub-activities__toggle--open': expanded.has(row.name) }"
										:aria-expanded="expanded.has(row.name)"
										:title="__('Show submittals, documents and dependencies')"
									>
										▸
									</button>
								</td>
								<td>
									<span class="hub-activities__indent" :style="{ width: (row.indent || 0) * 18 + 'px' }" />
									<a href="#" class="hub-link" @click.stop.prevent="open_detail(row.name)">{{ row.activity_code }}</a>
								</td>
								<td>
									{{ row.activity_name }}
									<span v-if="row.is_milestone" class="hub-activities__milestone" :title="__('Milestone')" />
								</td>
								<td>
									<a
										v-if="row.wbs_node"
										:href="`/app/egc-wbs-node/${encodeURIComponent(row.wbs_node)}`"
										:title="row.wbs_node"
										@click.stop
										>{{ row.wbs_label || row.wbs_node }}</a
									>
									<span v-else>—</span>
								</td>
								<td>{{ row.discipline || "—" }}</td>
								<td :class="{ 'hub-table__overdue': row.is_overdue }">{{ format_date(row.planned_start_date) }}</td>
								<td :class="{ 'hub-table__overdue': row.is_overdue }">
									{{ format_date(row.planned_end_date) }}
									<span v-if="row.is_overdue" class="hub-table__overdue-tag">{{ __("Overdue") }}</span>
								</td>
								<td>{{ format_duration(row.duration_days) }}</td>
								<td>{{ format_date(row.actual_end_date) }}</td>
								<td><StatusPill :status="row.status" /></td>
								<td>{{ format_weight(row.weight_pct) }}</td>
								<td>
									<div class="hub-percent">
										<div class="hub-percent__track">
											<div class="hub-percent__fill" :style="{ width: (row.percent_complete || 0) + '%' }" />
										</div>
										<span class="hub-percent__value">{{ Math.round(row.percent_complete || 0) }}%</span>
									</div>
								</td>
								<td>{{ row.responsible_user || row.responsible_supplier || "—" }}</td>
								<td v-if="can_write">
									<button
										type="button"
										class="btn btn-xs btn-default"
										:title="__('Add child activity')"
										@click.stop="open_quick_add(row)"
									>
										+
									</button>
								</td>
							</tr>
							<tr v-if="expanded.has(row.name)" class="hub-activities__expand-row">
								<td :colspan="column_count">
									<ActivityExpandPanel
										:activity="row.name"
										:project="project"
										:can-write="can_write"
										:link-counts="row.link_counts || {}"
										@open-detail="open_detail"
										@changed="reload"
									/>
								</td>
							</tr>
						</template>
					</tbody>
				</table>
			</div>
		</template>

		<ActivityDetail
			v-if="selected_activity"
			:activity="selected_activity"
			:project="project"
			:can-write="can_write"
			@close="close_detail"
			@changed="on_detail_changed"
			@open-activity="open_detail"
		/>
	</div>
</template>

<style scoped>
.hub-activities__indent {
	display: inline-block;
	vertical-align: middle;
}

.hub-activities__milestone {
	display: inline-block;
	width: 8px;
	height: 8px;
	margin-left: 6px;
	transform: rotate(45deg);
	background: var(--blue-500, var(--text-color));
	vertical-align: middle;
}

.hub-activities__toggle-col {
	width: 28px;
	padding-left: 10px !important;
	padding-right: 0 !important;
}

.hub-activities__toggle {
	appearance: none;
	border: none;
	background: none;
	padding: 0;
	width: 20px;
	height: 20px;
	line-height: 20px;
	text-align: center;
	color: var(--text-muted);
	cursor: pointer;
	font-size: var(--text-xs);
	transition: transform 0.1s ease;
}

.hub-activities__toggle:hover {
	color: var(--text-color);
}

.hub-activities__toggle--open {
	transform: rotate(90deg);
}

.hub-activities__expand-row td {
	padding: 0 !important;
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

.hub-toolbar__check {
	display: flex;
	align-items: center;
	gap: 6px;
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: nowrap;
}

.hub-table__overdue-tag {
	margin-left: 6px;
	font-size: var(--text-xs);
	font-weight: 600;
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
