<script setup>
import { computed, ref, watch, onMounted } from "vue";
import { get_submittals } from "../api";
import { create_submittal } from "./submittals_api";
import { useHubResource } from "../composables/useHubResource";
import { consumeOverdueIntent } from "../composables/useOverdueIntent";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";
import SubmittalDetail from "./SubmittalDetail.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { data, loading, error, reload } = useHubResource(() => get_submittals(props.project));
watch(() => props.project, reload, { immediate: true });

const WRITE_ROLES = ["EGC Project Manager", "EGC Project Engineer", "EGC Document Controller", "System Manager"];
const can_write = computed(() => (frappe.user_roles || []).some((role) => WRITE_ROLES.includes(role)));

const submittals_empty_state_description = __(
	"A Submittal is a formal review/approval process for a document revision — not every document needs one, only those requiring stakeholder sign-off (shop drawings, method statements, and the like). Start one here, or from a document's own page via Submit for Review."
);

const selected_submittal = ref(null);
function open_detail(name) {
	selected_submittal.value = name;
}
function close_detail() {
	selected_submittal.value = null;
}

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

function open_create_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("New Submittal"),
		fields: [
			{ fieldname: "submittal_number", fieldtype: "Data", label: __("Submittal Number"), reqd: 1 },
			{ fieldname: "title", fieldtype: "Data", label: __("Title"), reqd: 1 },
			{
				fieldname: "submittal_type",
				fieldtype: "Link",
				label: __("Submittal Type"),
				options: "EGC Submittal Type",
				reqd: 1,
			},
			{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline" },
			{
				fieldname: "wbs_node",
				fieldtype: "Link",
				label: __("WBS Node"),
				options: "EGC WBS Node",
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "responsible_organization",
				fieldtype: "Link",
				label: __("Responsible Organization"),
				options: "EGC Organization",
				description: __("Pick a Project Directory entry, or leave blank and type a one-off party below."),
			},
			{ fieldname: "responsible_party", fieldtype: "Data", label: __("Responsible Party") },
			{
				fieldname: "received_from_person",
				fieldtype: "Link",
				label: __("Received From (Person)"),
				options: "EGC Person",
				description: __("Pick a Project Directory entry, or leave blank and type a one-off party below."),
			},
			{ fieldname: "received_from", fieldtype: "Data", label: __("Received From") },
			{ fieldname: "submittal_manager", fieldtype: "Link", label: __("Submittal Manager"), options: "User" },
			{ fieldname: "description", fieldtype: "Small Text", label: __("Description") },
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			create_submittal(props.project, values)
				.then((result) => {
					dialog.hide();
					reload();
					open_detail(result.name);
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Create Submittal"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function on_detail_changed() {
	reload();
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
			:description="submittals_empty_state_description"
			:action-label="__('+ New Submittal')"
			@action="open_create_dialog"
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
				<button
					v-if="can_write"
					type="button"
					class="btn btn-sm btn-primary hub-submittals__new"
					@click="open_create_dialog"
				>
					{{ __("+ New Submittal") }}
				</button>
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
							<th>{{ __("Ball in Court") }}</th>
							<th>{{ __("Due Date") }}</th>
							<th>{{ __("Days Overdue") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in filtered"
							:key="row.name"
							class="hub-table__row--clickable"
							@click="open_detail(row.name)"
						>
							<td>{{ row.submittal_number }}</td>
							<td class="hub-table__truncate" :title="row.title">{{ row.title }}</td>
							<td>{{ row.submittal_type || "—" }}</td>
							<td>{{ row.discipline || "—" }}</td>
							<td>{{ row.current_submission_label || "—" }}</td>
							<td><StatusPill :status="row.submittal_status" /></td>
							<td>{{ row.ball_in_court || "—" }}</td>
							<td>{{ format_date(row.current_due_date) }}</td>
							<td :class="{ 'hub-table__overdue': row.is_overdue }">{{ days_overdue(row) }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</template>

		<SubmittalDetail
			v-if="selected_submittal"
			:submittal="selected_submittal"
			:project="project"
			:can-write="can_write"
			@close="close_detail"
			@changed="on_detail_changed"
		/>
	</div>
</template>

<style scoped>
.hub-submittals__new {
	margin-left: auto;
}

.hub-toolbar__check {
	display: flex;
	align-items: center;
	gap: 6px;
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: nowrap;
}
</style>
