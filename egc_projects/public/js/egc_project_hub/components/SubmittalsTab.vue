<script setup>
import { computed, ref, watch, onMounted } from "vue";
import { get_submittals } from "../api";
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

const { data, loading, error, reload } = useHubResource(() => get_submittals(props.project));
watch(() => props.project, reload, { immediate: true });

const status_filter = ref("");
const type_filter = ref("");
const overdue_only = ref(false);

onMounted(() => {
	if (consumeOverdueIntent("submittals")) overdue_only.value = true;
});

const statuses = computed(() =>
	[...new Set((data.value || []).map((r) => r.submittal_status).filter(Boolean))].sort()
);
const types = computed(() =>
	[...new Set((data.value || []).map((r) => r.submittal_type).filter(Boolean))].sort()
);

const filtered = computed(() => {
	return (data.value || []).filter((row) => {
		if (status_filter.value && row.submittal_status !== status_filter.value) return false;
		if (type_filter.value && row.submittal_type !== type_filter.value) return false;
		if (overdue_only.value && !row.is_overdue) return false;
		return true;
	});
});

function open_form(row) {
	frappe.set_route("Form", "EGC Submittal", row.name);
}

function create_submittal() {
	frappe.new_doc("EGC Submittal", { project: props.project });
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

function days_overdue(row) {
	if (!row.is_overdue || !row.current_due_date) return "—";
	return frappe.datetime.get_diff(frappe.datetime.now_date(), row.current_due_date);
}
</script>

<template>
	<div class="hub-submittals">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />
		<EmptyState
			v-else-if="!(data || []).length"
			:title="__('No submittals yet')"
			:description="__('Submittals track review cycles for controlled documents on this project.')"
			:action-label="__('New Submittal')"
			@action="create_submittal"
		/>

		<template v-else>
			<div class="hub-toolbar">
				<select v-model="status_filter">
					<option value="">{{ __("All Statuses") }}</option>
					<option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
				</select>
				<select v-model="type_filter">
					<option value="">{{ __("All Types") }}</option>
					<option v-for="t in types" :key="t" :value="t">{{ t }}</option>
				</select>
				<label class="hub-toolbar__check">
					<input v-model="overdue_only" type="checkbox" />
					{{ __("Overdue only") }}
				</label>
			</div>

			<EmptyState v-if="!filtered.length" :title="__('No submittals match these filters')" />
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
							<th>{{ __("Due Date") }}</th>
							<th>{{ __("Days Overdue") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in filtered"
							:key="row.name"
							class="hub-table__row--clickable"
							@click="open_form(row)"
						>
							<td>{{ row.submittal_number }}</td>
							<td>{{ row.title }}</td>
							<td>{{ row.submittal_type || "—" }}</td>
							<td>{{ row.discipline || "—" }}</td>
							<td>{{ row.current_submission_label || "—" }}</td>
							<td><StatusPill :status="row.submittal_status" /></td>
							<td>{{ format_date(row.current_due_date) }}</td>
							<td :class="{ 'hub-table__overdue': row.is_overdue }">{{ days_overdue(row) }}</td>
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
</style>
