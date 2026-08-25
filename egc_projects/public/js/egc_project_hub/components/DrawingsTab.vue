<script setup>
import { computed, ref, watch } from "vue";
import { get_drawings, get_document_revisions } from "../api";
import { useHubResource } from "../composables/useHubResource";
import { statusColor } from "../composables/useStatusColor";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { data, loading, error, reload } = useHubResource(() => get_drawings(props.project));
watch(() => props.project, reload, { immediate: true });

const discipline_filter = ref("");
const approval_filter = ref("");

const disciplines = computed(() =>
	[...new Set((data.value || []).map((r) => r.discipline).filter(Boolean))].sort()
);
const approval_statuses = computed(() =>
	[...new Set((data.value || []).map((r) => r.approval_status).filter(Boolean))].sort()
);

const filtered = computed(() => {
	return (data.value || []).filter((row) => {
		if (discipline_filter.value && row.discipline !== discipline_filter.value) return false;
		if (approval_filter.value && row.approval_status !== approval_filter.value) return false;
		return true;
	});
});

function open_form(row) {
	frappe.set_route("Form", "EGC Project Document", row.document);
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
			</div>

			<EmptyState v-if="!filtered.length" :title="__('No drawings match these filters')" />
			<div v-else class="hub-table-wrap">
				<table class="hub-table">
					<thead>
						<tr>
							<th>{{ __("Drawing No") }}</th>
							<th>{{ __("Title") }}</th>
							<th>{{ __("Discipline") }}</th>
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
							@click="open_form(row)"
						>
							<td>{{ row.number }}</td>
							<td>{{ row.title }}</td>
							<td>{{ row.discipline || "—" }}</td>
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
</style>
