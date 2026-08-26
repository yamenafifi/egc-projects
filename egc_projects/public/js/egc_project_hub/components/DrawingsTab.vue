<script setup>
import { computed, ref, watch } from "vue";
import { get_drawings, get_document_revisions } from "../api";
import { create_document } from "./documents_api";
import { useHubResource } from "../composables/useHubResource";
import { statusColor } from "../composables/useStatusColor";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";
import DocumentDetail from "./DocumentDetail.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { data, loading, error, reload } = useHubResource(() => get_drawings(props.project));
watch(() => props.project, reload, { immediate: true });

const WRITE_ROLES = ["EGC Project Manager", "EGC Project Engineer", "EGC Document Controller", "System Manager"];
const can_write = computed(() => (frappe.user_roles || []).some((role) => WRITE_ROLES.includes(role)));

const discipline_filter = ref("");
const approval_filter = ref("");
const set_filter = ref("");
const area_filter = ref("");

const disciplines = computed(() =>
	[...new Set((data.value || []).map((r) => r.discipline).filter(Boolean))].sort()
);
const approval_statuses = computed(() =>
	[...new Set((data.value || []).map((r) => r.approval_status).filter(Boolean))].sort()
);
const sets = computed(() => [...new Set((data.value || []).map((r) => r.drawing_set).filter(Boolean))].sort());
const areas = computed(() => [...new Set((data.value || []).map((r) => r.drawing_area).filter(Boolean))].sort());

const filtered = computed(() => {
	return (data.value || []).filter((row) => {
		if (discipline_filter.value && row.discipline !== discipline_filter.value) return false;
		if (approval_filter.value && row.approval_status !== approval_filter.value) return false;
		if (set_filter.value && row.drawing_set !== set_filter.value) return false;
		if (area_filter.value && row.drawing_area !== area_filter.value) return false;
		return true;
	});
});

const selected_document = ref(null);
function open_detail(row) {
	selected_document.value = row.document;
}
function close_detail() {
	selected_document.value = null;
}
function on_detail_changed() {
	reload();
}

function open_create_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("New Drawing"),
		fields: [
			{ fieldname: "document_number", fieldtype: "Data", label: __("Drawing Number"), reqd: 1 },
			{ fieldname: "title", fieldtype: "Data", label: __("Title"), reqd: 1 },
			{
				fieldname: "document_type",
				fieldtype: "Link",
				label: __("Document Type"),
				options: "EGC Document Type",
				reqd: 1,
				get_query: () => ({ filters: { is_drawing: 1 } }),
			},
			{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline" },
			{
				fieldname: "column_break_set",
				fieldtype: "Column Break",
			},
			{
				fieldname: "drawing_set",
				fieldtype: "Link",
				label: __("Drawing Set"),
				options: "EGC Drawing Set",
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "drawing_area",
				fieldtype: "Link",
				label: __("Drawing Area"),
				options: "EGC Drawing Area",
				get_query: () => ({ filters: { project: props.project } }),
			},
			{ fieldname: "drawing_date", fieldtype: "Date", label: __("Drawing Date") },
			{ fieldname: "received_date", fieldtype: "Date", label: __("Received Date") },
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
				.then((result) => {
					dialog.hide();
					reload();
					open_detail({ document: result.name });
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Create Drawing"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

function escape(value) {
	return frappe.utils.escape_html(value == null ? "" : String(value));
}

async function open_revision_history(row, event) {
	event.stopPropagation();
	const dialog = new frappe.ui.Dialog({
		title: __("Revision History — {0}", [row.number]),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "revisions" }],
	});
	dialog.show();
	dialog.set_value(
		"revisions",
		`<div class="text-muted">${__("Loading…")}</div>`
	);

	try {
		const revisions = await get_document_revisions(row.document);
		if (!revisions.length) {
			dialog.set_value("revisions", `<div class="text-muted">${__("No revisions recorded.")}</div>`);
			return;
		}
		const rows = revisions
			.map((rev) => {
				const color = statusColor(rev.revision_status);
				const file_link = rev.file
					? `<a href="${escape(rev.file)}" target="_blank" rel="noopener">${__("Open File")}</a>`
					: "—";
				return `<tr>
					<td>${escape(rev.revision)}</td>
					<td><span class="indicator-pill ${color}">${escape(rev.revision_status)}</span></td>
					<td>${escape(frappe.datetime.str_to_user(rev.revision_date))}</td>
					<td>${rev.issue_date ? escape(frappe.datetime.str_to_user(rev.issue_date)) : "—"}</td>
					<td>${file_link}</td>
					<td>${escape(rev.remarks || "—")}</td>
				</tr>`;
			})
			.join("");
		dialog.set_value(
			"revisions",
			`<table class="hub-table"><thead><tr>
				<th>${__("Revision")}</th><th>${__("Status")}</th><th>${__("Revision Date")}</th>
				<th>${__("Issue Date")}</th><th>${__("File")}</th><th>${__("Remarks")}</th>
			</tr></thead><tbody>${rows}</tbody></table>`
		);
	} catch (e) {
		dialog.set_value("revisions", `<div class="text-muted">${escape(e.message)}</div>`);
	}
}
</script>

<template>
	<div class="hub-drawings">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />
		<EmptyState
			v-else-if="!(data || []).length"
			:title="__('No drawings yet')"
			:description="__('The drawing register lists every controlled document flagged as a drawing.')"
			:action-label="can_write ? __('+ New Drawing') : ''"
			@action="open_create_dialog"
		/>

		<template v-else>
			<div class="hub-toolbar">
				<select v-model="discipline_filter">
					<option value="">{{ __("All Disciplines") }}</option>
					<option v-for="d in disciplines" :key="d" :value="d">{{ d }}</option>
				</select>
				<select v-model="approval_filter">
					<option value="">{{ __("All Approval Statuses") }}</option>
					<option v-for="s in approval_statuses" :key="s" :value="s">{{ s }}</option>
				</select>
				<select v-model="set_filter">
					<option value="">{{ __("All Sets") }}</option>
					<option v-for="s in sets" :key="s" :value="s">{{ s }}</option>
				</select>
				<select v-model="area_filter">
					<option value="">{{ __("All Areas") }}</option>
					<option v-for="a in areas" :key="a" :value="a">{{ a }}</option>
				</select>
				<button
					v-if="can_write"
					type="button"
					class="btn btn-sm btn-primary hub-drawings__new"
					@click="open_create_dialog"
				>
					{{ __("+ New Drawing") }}
				</button>
			</div>

			<EmptyState v-if="!filtered.length" :title="__('No drawings match these filters')" />
			<div v-else class="hub-table-wrap">
				<table class="hub-table">
					<thead>
						<tr>
							<th>{{ __("Drawing No") }}</th>
							<th>{{ __("Title") }}</th>
							<th>{{ __("Discipline") }}</th>
							<th>{{ __("Set") }}</th>
							<th>{{ __("Area") }}</th>
							<th>{{ __("Current Rev") }}</th>
							<th>{{ __("Approval Status") }}</th>
							<th>{{ __("Revision Date") }}</th>
							<th>{{ __("File") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in filtered"
							:key="row.document"
							class="hub-table__row--clickable"
							@click="open_detail(row)"
						>
							<td>{{ row.number }}</td>
							<td>{{ row.title }}</td>
							<td>{{ row.discipline || "—" }}</td>
							<td>{{ row.drawing_set || "—" }}</td>
							<td>{{ row.drawing_area || "—" }}</td>
							<td>
								<span
									v-if="row.current_revision_label"
									class="hub-link"
									@click="open_revision_history(row, $event)"
								>
									{{ row.current_revision_label }}
								</span>
								<span v-else>—</span>
							</td>
							<td><StatusPill :status="row.approval_status" /></td>
							<td>{{ format_date(row.current_revision_date) }}</td>
							<td>
								<a
									v-if="row.current_file"
									:href="row.current_file"
									target="_blank"
									rel="noopener"
									class="hub-link"
									@click.stop
								>
									{{ __("Open") }}
								</a>
								<span v-else>—</span>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</template>

		<DocumentDetail
			v-if="selected_document"
			:document="selected_document"
			@close="close_detail"
			@changed="on_detail_changed"
		/>
	</div>
</template>

<style scoped>
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

.hub-drawings__new {
	margin-left: auto;
}
</style>
