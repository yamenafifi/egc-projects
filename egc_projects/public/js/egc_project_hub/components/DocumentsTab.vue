<script setup>
import { computed, ref, watch } from "vue";
import { get_documents, create_document } from "./documents_api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";
import DocumentDetail from "./DocumentDetail.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { data, loading, error, reload } = useHubResource(() => get_documents(props.project));
watch(() => props.project, reload, { immediate: true });

const search = ref("");
const document_type_filter = ref("");
const discipline_filter = ref("");
const document_status_filter = ref("");
const approval_filter = ref("");

const selected_document = ref(null);

const document_types = computed(() =>
	[...new Set((data.value || []).map((r) => r.document_type).filter(Boolean))].sort()
);
const disciplines = computed(() =>
	[...new Set((data.value || []).map((r) => r.discipline).filter(Boolean))].sort()
);
const document_statuses = computed(() =>
	[...new Set((data.value || []).map((r) => r.document_status).filter(Boolean))].sort()
);
const approval_statuses = computed(() =>
	[...new Set((data.value || []).map((r) => r.approval_status).filter(Boolean))].sort()
);

const filtered = computed(() => {
	const term = search.value.trim().toLowerCase();
	return (data.value || []).filter((row) => {
		if (document_type_filter.value && row.document_type !== document_type_filter.value) return false;
		if (discipline_filter.value && row.discipline !== discipline_filter.value) return false;
		if (document_status_filter.value && row.document_status !== document_status_filter.value) return false;
		if (approval_filter.value && row.approval_status !== approval_filter.value) return false;
		if (
			term &&
			![row.document_number, row.title, row.originator].some((value) =>
				(value || "").toLowerCase().includes(term)
			)
		)
			return false;
		return true;
	});
});

function open_detail(document_name) {
	selected_document.value = document_name;
}

function close_detail() {
	selected_document.value = null;
}

function on_changed() {
	reload();
}

function open_create_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("New Document"),
		fields: [
			{ fieldname: "document_number", fieldtype: "Data", label: __("Document Number"), reqd: 1 },
			{ fieldname: "title", fieldtype: "Data", label: __("Title"), reqd: 1 },
			{
				fieldname: "document_type",
				fieldtype: "Link",
				label: __("Document Type"),
				options: "EGC Document Type",
				reqd: 1,
			},
			{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline" },
			{
				fieldname: "originator_person",
				fieldtype: "Link",
				label: __("Originator (Person)"),
				options: "EGC Person",
				description: __("Pick a Project Directory entry, or leave blank and type a one-off party below."),
			},
			{ fieldname: "originator", fieldtype: "Data", label: __("Originator") },
			{
				fieldname: "wbs_node",
				fieldtype: "Link",
				label: __("WBS Node"),
				options: "EGC WBS Node",
				get_query: () => ({ filters: { project: props.project } }),
			},
			{ fieldname: "description", fieldtype: "Small Text", label: __("Description") },
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			create_document({ project: props.project, ...values })
				.then((doc) => {
					dialog.hide();
					reload();
					open_detail(doc.name);
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Create Document"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}
</script>

<template>
	<div class="hub-documents">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />
		<EmptyState
			v-else-if="!(data || []).length"
			:title="__('No controlled documents yet')"
			:description="
				__('Every controlled document on this project lives here — drawings and non-drawing documents alike.')
			"
			:action-label="__('New Document')"
			@action="open_create_dialog"
		/>

		<template v-else>
			<div class="hub-toolbar">
				<input v-model="search" type="text" :placeholder="__('Search number, title, originator…')" />
				<select v-model="document_type_filter">
					<option value="">{{ __("All Document Types") }}</option>
					<option v-for="t in document_types" :key="t" :value="t">{{ t }}</option>
				</select>
				<select v-model="discipline_filter">
					<option value="">{{ __("All Disciplines") }}</option>
					<option v-for="d in disciplines" :key="d" :value="d">{{ d }}</option>
				</select>
				<select v-model="document_status_filter">
					<option value="">{{ __("All Document Statuses") }}</option>
					<option v-for="s in document_statuses" :key="s" :value="s">{{ s }}</option>
				</select>
				<select v-model="approval_filter">
					<option value="">{{ __("All Approval Statuses") }}</option>
					<option v-for="s in approval_statuses" :key="s" :value="s">{{ s }}</option>
				</select>
				<button type="button" class="btn btn-sm btn-primary hub-documents__new" @click="open_create_dialog">
					{{ __("+ New Document") }}
				</button>
			</div>

			<EmptyState v-if="!filtered.length" :title="__('No documents match these filters')" />
			<div v-else class="hub-table-wrap">
				<table class="hub-table">
					<thead>
						<tr>
							<th>{{ __("Document Number") }}</th>
							<th>{{ __("Title") }}</th>
							<th>{{ __("Document Type") }}</th>
							<th>{{ __("Discipline") }}</th>
							<th>{{ __("Current Revision") }}</th>
							<th>{{ __("Document Status") }}</th>
							<th>{{ __("Approval Status") }}</th>
							<th>{{ __("Originator") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in filtered"
							:key="row.document"
							class="hub-table__row--clickable"
							@click="open_detail(row.document)"
						>
							<td>{{ row.document_number }}</td>
							<td class="hub-table__truncate" :title="row.title">{{ row.title }}</td>
							<td>{{ row.document_type }}</td>
							<td>{{ row.discipline || "—" }}</td>
							<td>{{ row.current_revision_label || "—" }}</td>
							<td><StatusPill :status="row.document_status" /></td>
							<td><StatusPill :status="row.approval_status" /></td>
							<td>{{ row.originator || "—" }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</template>

		<DocumentDetail
			v-if="selected_document"
			:document="selected_document"
			@close="close_detail"
			@changed="on_changed"
		/>
	</div>
</template>

<style scoped>
.hub-documents__new {
	margin-left: auto;
}
</style>
