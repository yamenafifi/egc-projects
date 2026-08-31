<script setup>
import { computed, ref, watch, onMounted } from "vue";
import { get_documents, create_document, create_document_revision, get_drawing_document_types } from "./documents_api";
import { get_directory_person_emails, person_link_filter } from "./directory_helpers";
import { openExportDialog, openImportDialog, confirmBulkDelete } from "./bulk_transfer_flow";
import { useRowSelection } from "../composables/useRowSelection";
import BulkActionsBar from "./BulkActionsBar.vue";
import { useHubResource } from "../composables/useHubResource";
import { consumeDrawingsApprovalIntent } from "../composables/useDrawingsIntent";
import { consumeOpenDocumentIntent } from "../composables/useOpenDocumentIntent";
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

// A client-side hint only, same discipline as every write action elsewhere in this Hub — matches
// the roles actually granted `delete` on EGC Project Document (System Manager/Document
// Controller/Project Manager, not Engineer). Only gates the bulk "Delete Selected" action; every
// other write path in this file relies purely on the server-side check, unchanged.
const DELETE_ROLES = ["System Manager", "EGC Document Controller", "EGC Project Manager"];
const can_write = computed(() => (frappe.user_roles || []).some((role) => DELETE_ROLES.includes(role)));

const documents_empty_state_description = __(
	"Every controlled document on this project lives here — drawings and non-drawing documents alike. Not every document needs formal review; use Submit for Review on a document, or the Submittals tab, only for the ones that do."
);

const search = ref("");
const document_type_filter = ref("");
const discipline_filter = ref("");
const document_status_filter = ref("");
const approval_filter = ref("");

// A Drawing isn't a separate record — it's an EGC Project Document whose Document Type is
// flagged is_drawing=1 (see api/documents.py's get_drawing_document_types). This tab used to
// have a twin, DrawingsTab.vue, that just pre-filtered the exact same list with its own parallel
// toolbar and create dialog; folded in here as a toggle instead of a second tab.
const drawing_types = ref([]);
const drawings_only = ref(false);
const set_filter = ref("");
const area_filter = ref("");

const selected_document = ref(null);

onMounted(async () => {
	const approval_intent = consumeDrawingsApprovalIntent();
	if (approval_intent) {
		drawings_only.value = true;
		approval_filter.value = approval_intent;
	}
	// Cross-nav from SubmittalDetail.vue's tracked documents — open straight into this specific
	// document's detail drawer instead of just landing on the unfiltered register.
	const open_document_intent = consumeOpenDocumentIntent();
	if (open_document_intent) selected_document.value = open_document_intent;
	try {
		drawing_types.value = await get_drawing_document_types();
	} catch (e) {
		// Non-fatal — the "Drawings only" toggle just has nothing to match against.
	}
});

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
const sets = computed(() => [...new Set((data.value || []).map((r) => r.drawing_set).filter(Boolean))].sort());
const areas = computed(() => [...new Set((data.value || []).map((r) => r.drawing_area).filter(Boolean))].sort());

function is_drawing(row) {
	return drawing_types.value.includes(row.document_type);
}

const filtered = computed(() => {
	const term = search.value.trim().toLowerCase();
	return (data.value || []).filter((row) => {
		if (drawings_only.value && !is_drawing(row)) return false;
		if (document_type_filter.value && row.document_type !== document_type_filter.value) return false;
		if (discipline_filter.value && row.discipline !== discipline_filter.value) return false;
		if (document_status_filter.value && row.document_status !== document_status_filter.value) return false;
		if (approval_filter.value && row.approval_status !== approval_filter.value) return false;
		if (drawings_only.value && set_filter.value && row.drawing_set !== set_filter.value) return false;
		if (drawings_only.value && area_filter.value && row.drawing_area !== area_filter.value) return false;
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

const {
	selected: selected_rows,
	selected_count,
	all_selected,
	some_selected,
	is_selected,
	toggle,
	toggle_all,
	clear,
} = useRowSelection(filtered, (row) => row.document);

function open_bulk_export() {
	openExportDialog({
		project: props.project,
		doctype: "EGC Project Document",
		label: __("Documents"),
		selectedNames: [...selected_rows.value],
	});
}

function open_bulk_delete() {
	confirmBulkDelete({
		project: props.project,
		doctype: "EGC Project Document",
		label: __("Documents"),
		selectedNames: [...selected_rows.value],
		onDeleted: () => {
			clear();
			reload();
		},
	});
}

// A document Under Review shows who owes the next action right in the register (its governing
// Submittal's ball_in_court/due date, batched server-side in api/documents.py.get_documents —
// docs/ARCHITECTURE_V2.md's Documents/Submittals redesign) instead of only after opening the
// detail drawer and scrolling to "Related Submittals".
function is_overdue(due_date) {
	return Boolean(due_date) && frappe.datetime.get_diff(frappe.datetime.now_date(), due_date) > 0;
}

function days_overdue(due_date) {
	return frappe.datetime.get_diff(frappe.datetime.now_date(), due_date);
}

function open_detail(document_name) {
	selected_document.value = document_name;
}

function close_detail() {
	selected_document.value = null;
}

function on_changed() {
	reload();
}

function open_export_dialog() {
	openExportDialog({ project: props.project, doctype: "EGC Project Document", label: __("Documents") });
}

function open_import_dialog() {
	openImportDialog({
		project: props.project,
		doctype: "EGC Project Document",
		label: __("Documents"),
		onImported: reload,
	});
}

// Anchors the two Attach fields below at the Project record (which already exists) rather than
// leaving `doctype`/`docname` blank — a bare `frappe.ui.Dialog` Attach control with no `options`
// uploads with an empty `attached_to_doctype`, which is invisible to /app/file and to any
// attached_to_*-filtered permission check (the exact bug `DocumentDetail.vue`'s own "New
// Revision" dialog already documents and works around). The Document being created doesn't exist
// yet at upload time — unlike that dialog, which only ever runs against an already-existing
// Document — so there is no real record of this doctype to point at yet; the Project is the
// nearest real, already-existing, permission-checked anchor. The `fieldname` given here is
// bookkeeping only (Project has no field that actually holds this URL) — same non-requirement
// the existing "New Revision" workaround already relies on.
function file_anchor() {
	return { doctype: "Project", docname: props.project, fieldname: "notes" };
}

async function open_create_dialog() {
	// Direct user instruction: Originator must be strictly a Project Directory person, no
	// free-text fallback in this form (the underlying field still allows one for old/other
	// callers — see directory_helpers.js). Fetched before building the dialog so the Link
	// field's own get_query filter is final from the first render, not patched in later.
	const directory_emails = await get_directory_person_emails(props.project);

	const dialog = new frappe.ui.Dialog({
		title: __("New Document"),
		size: "large",
		fields: [
			{ fieldname: "document_number", fieldtype: "Data", label: __("Document Number"), reqd: 1 },
			{ fieldname: "title", fieldtype: "Data", label: __("Title"), reqd: 1 },
			{ fieldtype: "Column Break" },
			{
				fieldname: "document_type",
				fieldtype: "Link",
				label: __("Document Type"),
				options: "EGC Document Type",
				reqd: 1,
				// The one, single behavior the user specifically called out as missing: Drawing
				// fields (and the Native File attachment below) only ever appear once the picked
				// type is actually a drawing type — never a "(optional, only meaningful if...)"
				// section shown regardless and left to the user to ignore correctly.
				onchange: () => toggle_drawing_fields(dialog),
			},
			{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline" },

			{ fieldtype: "Section Break" },
			{
				fieldname: "originator_person",
				fieldtype: "Link",
				label: __("Originator"),
				options: "User",
				reqd: 1,
				description: __("Must already be on this project's Directory — add them there first if they're missing."),
				get_query: person_link_filter(directory_emails),
			},
			{
				fieldname: "wbs_node",
				fieldtype: "Link",
				label: __("WBS Node"),
				options: "EGC WBS Node",
				get_query: () => ({ filters: { project: props.project } }),
			},
			{ fieldtype: "Column Break" },
			{ fieldname: "description", fieldtype: "Small Text", label: __("Description") },

			{ fieldname: "drawing_section", fieldtype: "Section Break", label: __("Drawing Details"), hidden: 1 },
			{
				fieldname: "drawing_set",
				fieldtype: "Link",
				label: __("Drawing Set"),
				options: "EGC Drawing Set",
				hidden: 1,
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "drawing_area",
				fieldtype: "Link",
				label: __("Drawing Area"),
				options: "EGC Drawing Area",
				hidden: 1,
				get_query: () => ({ filters: { project: props.project } }),
			},
			{ fieldtype: "Column Break" },
			{ fieldname: "drawing_date", fieldtype: "Date", label: __("Drawing Date"), hidden: 1 },
			{ fieldname: "received_date", fieldtype: "Date", label: __("Received Date"), hidden: 1 },

			// The second explicitly-called-out gap: creating a Document never asked for a file at
			// all — you had to save it, THEN separately find "New Revision" to attach anything.
			// This is now one continuous action: the document AND its first revision, together.
			{ fieldtype: "Section Break", label: __("First Revision") },
			{ fieldname: "revision", fieldtype: "Data", label: __("Revision"), default: "00", reqd: 1 },
			{
				fieldname: "revision_date",
				fieldtype: "Date",
				label: __("Revision Date"),
				default: frappe.datetime.get_today(),
				reqd: 1,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "file",
				fieldtype: "Attach",
				label: __("File"),
				reqd: 1,
				options: file_anchor(),
			},
			{
				fieldname: "native_file",
				fieldtype: "Attach",
				label: __("Native File (e.g. .dwg)"),
				hidden: 1,
				description: __("Optional — the native authoring file, alongside File above. Same revision, two attachments."),
				options: file_anchor(),
			},
		],
		primary_action_label: __("Create Document"),
		async primary_action(values) {
			dialog.disable_primary_action();
			// Once create_document() succeeds, it's a real row in the database — the revision
			// step failing afterward must not be reported as though nothing happened.
			let created_document = null;
			try {
				created_document = (
					await create_document({
						project: props.project,
						document_number: values.document_number,
						title: values.title,
						document_type: values.document_type,
						discipline: values.discipline,
						originator_person: values.originator_person,
						wbs_node: values.wbs_node,
						description: values.description,
						drawing_set: values.drawing_set,
						drawing_area: values.drawing_area,
						drawing_date: values.drawing_date,
						received_date: values.received_date,
					})
				).name;

				await create_document_revision({
					document: created_document,
					revision: values.revision,
					file: values.file,
					native_file: values.native_file || undefined,
					revision_date: values.revision_date,
				});

				dialog.hide();
				reload();
				open_detail(created_document);
			} catch (e) {
				if (created_document) {
					dialog.hide();
					reload();
					open_detail(created_document);
					frappe.msgprint({
						title: __("Document Created, But Incomplete"),
						message: __("{0} was created, but the revision failed: {1} Add it from the document's own page.", [
							frappe.utils.escape_html(created_document),
							e.message,
						]),
						indicator: "orange",
					});
				} else {
					dialog.enable_primary_action();
					frappe.msgprint({ title: __("Could Not Create Document"), message: e.message, indicator: "red" });
				}
			}
		},
	});
	dialog.show();
}

function toggle_drawing_fields(dialog) {
	const is_drawing = drawing_types.value.includes(dialog.get_value("document_type"));
	for (const fieldname of ["drawing_section", "drawing_set", "drawing_area", "drawing_date", "received_date", "native_file"]) {
		dialog.set_df_property(fieldname, "hidden", !is_drawing);
	}
}
</script>

<template>
	<div class="hub-documents">
		<DocumentDetail
			v-if="selected_document"
			:document="selected_document"
			@close="close_detail"
			@changed="on_changed"
		/>

		<template v-else>
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />
		<EmptyState
			v-else-if="!(data || []).length"
			:title="__('No controlled documents yet')"
			:description="documents_empty_state_description"
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
				<label class="hub-toolbar__check">
					<input v-model="drawings_only" type="checkbox" />
					{{ __("Drawings only") }}
				</label>
				<template v-if="drawings_only">
					<select v-model="set_filter">
						<option value="">{{ __("All Sets") }}</option>
						<option v-for="s in sets" :key="s" :value="s">{{ s }}</option>
					</select>
					<select v-model="area_filter">
						<option value="">{{ __("All Areas") }}</option>
						<option v-for="a in areas" :key="a" :value="a">{{ a }}</option>
					</select>
				</template>
				<button type="button" class="btn btn-xs btn-default hub-documents__new" @click="open_export_dialog">
					{{ __("Export") }}
				</button>
				<button type="button" class="btn btn-xs btn-default" @click="open_import_dialog">
					{{ __("Import") }}
				</button>
				<button type="button" class="btn btn-sm btn-primary" @click="open_create_dialog">
					{{ __("+ New Document") }}
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

			<EmptyState v-if="!filtered.length" :title="__('No documents match these filters')" />
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
							<th>{{ __("Document Number") }}</th>
							<th>{{ __("Title") }}</th>
							<th>{{ __("Document Type") }}</th>
							<th>{{ __("Discipline") }}</th>
							<template v-if="drawings_only">
								<th>{{ __("Set") }}</th>
								<th>{{ __("Area") }}</th>
							</template>
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
							<td class="hub-table__check-col" @click.stop>
								<input type="checkbox" :checked="is_selected(row)" @change="toggle(row)" />
							</td>
							<td>{{ row.document_number }}</td>
							<td class="hub-table__truncate" :title="row.title">{{ row.title }}</td>
							<td>{{ row.document_type }}</td>
							<td>{{ row.discipline || "—" }}</td>
							<template v-if="drawings_only">
								<td>{{ row.drawing_set || "—" }}</td>
								<td>{{ row.drawing_area || "—" }}</td>
							</template>
							<td>{{ row.current_revision_label || "—" }}</td>
							<td><StatusPill :status="row.document_status" /></td>
							<td>
								<StatusPill :status="row.approval_status" />
								<div v-if="row.approval_status === 'Under Review' && row.ball_in_court" class="hub-table__subtext">
									{{ row.ball_in_court }}
									<span v-if="is_overdue(row.submittal_due_date)" class="hub-table__subtext--overdue">
										— {{ __("{0} overdue", [days_overdue(row.submittal_due_date)]) }}
									</span>
								</div>
							</td>
							<td>{{ row.originator || "—" }}</td>
						</tr>
					</tbody>
				</table>
			</div>
		</template>
		</template>
	</div>
</template>

<style scoped>
.hub-documents__new {
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

.hub-table__subtext {
	margin-top: 2px;
	font-size: var(--text-xs);
	color: var(--text-muted);
	white-space: nowrap;
}

.hub-table__subtext--overdue {
	color: var(--red-500, var(--text-on-red));
	font-weight: 500;
}
</style>
