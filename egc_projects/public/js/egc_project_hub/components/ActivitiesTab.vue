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
import ActivityGanttView from "./ActivityGanttView.vue";
import ActivityOutlineView from "./ActivityOutlineView.vue";

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

const status_filter = ref("");
const discipline_filter = ref("");
const overdue_only = ref(false);
const search = ref("");

// -- view switch: Table (flat, filterable — the default) / Gantt / Outline (collapsible tree) ---
const VIEWS = ["Table", "Gantt", "Outline"];
const active_view = ref("Table");

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
	// Root-level creation — same in-Hub dialog as the per-row "+" quick-add (open_quick_add
	// below), just without a parent. A persistent toolbar action, not just the empty-state's
	// one-time affordance: a project with activities already in it still needs a way to add a
	// new top-level phase without leaving the Hub for the native form.
	const dialog = new frappe.ui.Dialog({
		title: __("New Activity"),
		fields: [
			{ fieldname: "activity_code", fieldtype: "Data", label: __("Activity Code"), reqd: 1 },
			{ fieldname: "activity_name", fieldtype: "Data", label: __("Activity Name"), reqd: 1 },
			{ fieldname: "is_group", fieldtype: "Check", label: __("Is Group") },
			{
				fieldname: "wbs_node",
				fieldtype: "Link",
				label: __("WBS Node"),
				options: "EGC WBS Node",
				get_query: () => ({ filters: { project: props.project } }),
			},
			{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline" },
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			create_activity_record({ ...values, project: props.project })
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

// `row.link_counts` is already batched in one query per get_activities() call (api/hub.py) — a
// glanceable "2 Sub · 1 Doc" badge right on the collapsed row, so a PM scanning the whole list
// can already see what's underneath an Activity without expanding every row one at a time.
function link_badge(row, link_doctype) {
	return (row.link_counts || {})[link_doctype] || 0;
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
				<div class="hub-view-switch">
					<button
						v-for="view in VIEWS"
						:key="view"
						type="button"
						class="hub-view-switch__btn"
						:class="{ 'hub-view-switch__btn--active': active_view === view }"
						@click="active_view = view"
					>
						{{ __(view) }}
					</button>
				</div>
				<input v-if="active_view !== 'Gantt'" v-model="search" type="text" :placeholder="__('Search code or name…')" />
				<select v-if="active_view !== 'Gantt'" v-model="status_filter">
					<option value="">{{ __("All Statuses") }}</option>
					<option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
				</select>
				<select v-if="active_view !== 'Gantt'" v-model="discipline_filter">
					<option value="">{{ __("All Disciplines") }}</option>
					<option v-for="d in disciplines" :key="d" :value="d">{{ d }}</option>
				</select>
				<label v-if="active_view !== 'Gantt'" class="hub-toolbar__check">
					<input v-model="overdue_only" type="checkbox" />
					{{ __("Overdue only") }}
				</label>
				<div class="hub-toolbar__spacer" />
				<button v-if="can_write" type="button" class="btn btn-sm btn-primary" @click="create_activity">
					{{ __("+ New Activity") }}
				</button>
			</div>

			<ActivityGanttView v-if="active_view === 'Gantt'" :project="project" @open-activity="open_detail" />

			<ActivityOutlineView
				v-else-if="active_view === 'Outline'"
				:rows="filtered"
				@open-activity="open_detail"
			/>

			<template v-else>
				<EmptyState v-if="!filtered.length" :title="__('No activities match these filters')" />
				<div v-else class="hub-table-wrap">
				<table class="hub-table">
					<thead>
						<tr>
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
							<tr class="hub-table__row--clickable" @click="open_detail(row.name)">
								<td>
									<span class="hub-activities__indent" :style="{ width: (row.indent || 0) * 18 + 'px' }" />
									<a href="#" class="hub-link" @click.stop.prevent="open_detail(row.name)">{{ row.activity_code }}</a>
								</td>
								<td class="hub-table__truncate" :title="row.activity_name">
									{{ row.activity_name }}
									<span v-if="row.is_milestone" class="hub-activities__milestone" :title="__('Milestone')" />
									<span v-if="link_badge(row, 'EGC Submittal')" class="hub-activities__link-badge" :title="__('Linked Submittals')">
										{{ link_badge(row, "EGC Submittal") }} {{ __("Sub") }}
									</span>
									<span
										v-if="link_badge(row, 'EGC Project Document')"
										class="hub-activities__link-badge"
										:title="__('Linked Drawings & Documents')"
									>
										{{ link_badge(row, "EGC Project Document") }} {{ __("Doc") }}
									</span>
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
								<td class="hub-activities__assignees">
									<template v-if="row.assignees && row.assignees.length">
										<span
											v-for="(a, idx) in row.assignees.slice(0, 2)"
											:key="idx"
											class="hub-activities__assignee-chip"
											:title="a.assignment_role"
										>
											{{ a.label }}
										</span>
										<span v-if="row.assignees.length > 2" class="hub-activities__assignee-more">
											+{{ row.assignees.length - 2 }}
										</span>
									</template>
									<span v-else>—</span>
								</td>
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
						</template>
					</tbody>
				</table>
			</div>
		</template>
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

.hub-activities__assignees {
	display: flex;
	align-items: center;
	gap: 4px;
}

.hub-activities__assignee-chip {
	display: inline-block;
	padding: 2px 8px;
	font-size: var(--text-xs);
	font-weight: 500;
	color: var(--text-color);
	background: var(--control-bg);
	border-radius: var(--border-radius-full);
	white-space: nowrap;
}

.hub-activities__assignee-more {
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.hub-activities__link-badge {
	display: inline-block;
	margin-left: 6px;
	padding: 0 6px;
	font-size: var(--text-xs);
	font-weight: 500;
	color: var(--text-muted);
	background: var(--control-bg);
	border-radius: var(--border-radius-full);
	vertical-align: middle;
	white-space: nowrap;
}

.hub-view-switch {
	display: flex;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	overflow: hidden;
	flex: 0 0 auto;
}

.hub-view-switch__btn {
	appearance: none;
	border: none;
	background: var(--fg-color);
	color: var(--text-muted);
	padding: 5px 12px;
	font-size: var(--text-sm);
	cursor: pointer;
}

.hub-view-switch__btn + .hub-view-switch__btn {
	border-left: 1px solid var(--border-color);
}

.hub-view-switch__btn:hover {
	color: var(--text-color);
}

.hub-view-switch__btn--active {
	background: var(--control-bg);
	color: var(--text-color);
	font-weight: 600;
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

.hub-toolbar__spacer {
	flex: 1 1 auto;
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
