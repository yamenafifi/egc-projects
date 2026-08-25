<script setup>
import { computed, ref, watch, onMounted } from "vue";
import { get_activities } from "../api";
import { useHubResource } from "../composables/useHubResource";
import { consumeOverdueIntent } from "../composables/useOverdueIntent";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { data, loading, error, reload } = useHubResource(() => get_activities(props.project));
watch(() => props.project, reload, { immediate: true });

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

function open_form(row) {
	frappe.set_route("Form", "EGC Activity", row.name);
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
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
							<th>{{ __("Code") }}</th>
							<th>{{ __("Name") }}</th>
							<th>{{ __("WBS") }}</th>
							<th>{{ __("Discipline") }}</th>
							<th>{{ __("Planned Start") }}</th>
							<th>{{ __("Planned Finish") }}</th>
							<th>{{ __("Status") }}</th>
							<th>{{ __("% Complete") }}</th>
							<th>{{ __("Responsible") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in filtered"
							:key="row.name"
							class="hub-table__row--clickable"
							@click="open_form(row)"
						>
							<td>{{ row.activity_code }}</td>
							<td>{{ row.activity_name }}</td>
							<td>{{ row.wbs_node || "—" }}</td>
							<td>{{ row.discipline || "—" }}</td>
							<td :class="{ 'hub-table__overdue': row.is_overdue }">{{ format_date(row.planned_start_date) }}</td>
							<td :class="{ 'hub-table__overdue': row.is_overdue }">
								{{ format_date(row.planned_end_date) }}
								<span v-if="row.is_overdue" class="hub-table__overdue-tag">{{ __("Overdue") }}</span>
							</td>
							<td><StatusPill :status="row.status" /></td>
							<td>
								<div class="hub-percent">
									<div class="hub-percent__track">
										<div class="hub-percent__fill" :style="{ width: (row.percent_complete || 0) + '%' }" />
									</div>
									<span class="hub-percent__value">{{ Math.round(row.percent_complete || 0) }}%</span>
								</div>
							</td>
							<td>{{ row.responsible_user || "—" }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</template>
	</div>
</template>

<style scoped>
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
