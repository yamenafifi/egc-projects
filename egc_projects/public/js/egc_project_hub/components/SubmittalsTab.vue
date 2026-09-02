<script setup>
import { computed, ref, watch, onMounted } from "vue";
import { get_submittals } from "../api";
import { openSubmitForReviewFlow } from "./submit_for_review_flow";
import { openManageWorkflowTemplatesFlow } from "./workflow_template_flow";
import { openExportDialog, openImportDialog, confirmBulkDelete } from "./bulk_transfer_flow";
import { useRowSelection } from "../composables/useRowSelection";
import BulkActionsBar from "./BulkActionsBar.vue";
import { useHubResource } from "../composables/useHubResource";
import { consumeOverdueIntent } from "../composables/useOverdueIntent";
import { consumeOpenSubmittalIntent } from "../composables/useOpenSubmittalIntent";
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
	// Cross-nav from DocumentDetail.vue's "Related Submittals" — open straight into this specific
	// submittal's full-page detail instead of just landing on the unfiltered register.
	const open_submittal_intent = consumeOpenSubmittalIntent();
	if (open_submittal_intent) open_detail(open_submittal_intent);
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

const {
	selected: selected_rows,
	selected_count,
	all_selected,
	some_selected,
	is_selected,
	toggle,
	toggle_all,
	clear,
} = useRowSelection(filtered);

function open_bulk_export() {
	openExportDialog({
		project: props.project,
		doctype: "EGC Submittal",
		label: __("Submittals"),
		selectedNames: [...selected_rows.value],
	});
}

function open_bulk_delete() {
	confirmBulkDelete({
		project: props.project,
		doctype: "EGC Submittal",
		label: __("Submittals"),
		selectedNames: [...selected_rows.value],
		onDeleted: () => {
			clear();
			reload();
		},
	});
}

function open_create_dialog() {
	// Same shared flow DocumentDetail.vue's "Submit for Review" uses — creating a Submittal
	// always includes picking the document(s) it's about and setting up its review, never a
	// bare identity-only record (docs/ARCHITECTURE_V2.md's Documents/Submittals redesign).
	openSubmitForReviewFlow({
		project: props.project,
		onCreated(name) {
			reload();
			open_detail(name);
		},
	});
}

function on_detail_changed() {
	reload();
}

function open_export_dialog() {
	openExportDialog({ project: props.project, doctype: "EGC Submittal", label: __("Submittals") });
}

function open_manage_templates_dialog() {
	// Global, not project-scoped — a template is a reusable review sequence any project can
	// apply, matching EGC Submittal Workflow Template's own shape (no project field).
	openManageWorkflowTemplatesFlow({});
}

function open_import_dialog() {
	openImportDialog({
		project: props.project,
		doctype: "EGC Submittal",
		label: __("Submittals"),
		onImported: reload,
	});
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
		<SubmittalDetail
			v-if="selected_submittal"
			:submittal="selected_submittal"
			:project="project"
			:can-write="can_write"
			@close="close_detail"
			@changed="on_detail_changed"
		/>

		<template v-else>
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
				<button type="button" class="btn btn-xs btn-default hub-submittals__new" @click="open_export_dialog">
					{{ __("Export") }}
				</button>
				<button v-if="can_write" type="button" class="btn btn-xs btn-default" @click="open_import_dialog">
					{{ __("Import") }}
				</button>
				<button v-if="can_write" type="button" class="btn btn-xs btn-default" @click="open_manage_templates_dialog">
					{{ __("Workflow Templates") }}
				</button>
				<button
					v-if="can_write"
					type="button"
					class="btn btn-sm btn-primary"
					@click="open_create_dialog"
				>
					{{ __("+ New Submittal") }}
				</button>
			</div>

			<BulkActionsBar
				v-if="selected_count"
				:selected-count="selected_count"
				:can-delete="can_write"
				@export="open_bulk_export"
				@delete="open_bulk_delete"
				@clear="clear"
			/>

			<EmptyState v-if="!filtered.length" :title="__('No submittals match these filters')" />
			<div v-else class="hub-table-wrap">
				<table class="hub-table">
					<thead>
						<tr>
							<th class="hub-table__check-col">
								<input
									type="checkbox"
									:checked="all_selected"
									:ref="(el) => el && (el.indeterminate = some_selected)"
									:title="__('Select all')"
									@click.stop="toggle_all"
								/>
							</th>
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
							<td class="hub-table__check-col" @click.stop>
								<input type="checkbox" :checked="is_selected(row)" @change="toggle(row)" />
							</td>
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
		</template>
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
