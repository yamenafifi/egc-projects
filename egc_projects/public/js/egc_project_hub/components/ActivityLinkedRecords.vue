<!-- Read-only display + add/remove for one `link_doctype` slice of `EGC Activity Link` rows.
     Used twice by ActivityDetail.vue (Submittals tab: EGC Submittal, Drawings tab: EGC Project
     Document) so the two near-identical lists share one implementation instead of being copied.
     Mirrors the intent of `egc_activity_links.js`'s "Linked Documents & Submittals" section
     (same underlying EGC Activity Link data, same add/remove verbs) without calling into that
     vanilla-JS file, which renders into a jQuery `frm.dashboard` section, a different layer. -->
<script setup>
import { link_activity_record, unlink_activity_record } from "./activities_api";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps({
	activity: { type: String, required: true },
	project: { type: String, required: true },
	linkDoctype: { type: String, required: true },
	title: { type: String, required: true },
	emptyMessage: { type: String, required: true },
	rows: { type: Array, default: () => [] },
	canWrite: { type: Boolean, default: false },
});
const emit = defineEmits(["changed"]);

const LINK_PURPOSES = ["Reference", "Requirement"];

function row_number(row) {
	return row.document_number || row.submittal_number || "";
}

function row_current(row) {
	return row.current_revision_label || row.current_submission_label || "";
}

function row_status(row) {
	return row.approval_status || row.submittal_status || "";
}

function open_record(row) {
	frappe.set_route("Form", props.linkDoctype, row.link_name);
}

function open_add_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Link {0}", [props.title]),
		fields: [
			{
				fieldname: "link_name",
				fieldtype: "Link",
				label: props.title,
				options: props.linkDoctype,
				reqd: 1,
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "link_purpose",
				fieldtype: "Select",
				label: __("Purpose"),
				options: LINK_PURPOSES,
				default: LINK_PURPOSES[0],
			},
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			link_activity_record(props.activity, props.linkDoctype, values.link_name, values.link_purpose, values.remarks)
				.then(() => {
					dialog.hide();
					emit("changed");
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Link"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_remove(row) {
	frappe.confirm(__("Remove this link?"), () => {
		unlink_activity_record(row.name)
			.then(() => emit("changed"))
			.catch((e) => {
				frappe.msgprint({ title: __("Could Not Remove Link"), message: e.message, indicator: "red" });
			});
	});
}
</script>

<template>
	<div class="activity-links">
		<div class="activity-links__head">
			<div class="activity-detail__section-title">{{ title }}</div>
			<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_add_dialog">
				{{ __("Link Existing") }}
			</button>
		</div>
		<EmptyState v-if="!rows.length" :title="emptyMessage" />
		<ul v-else class="activity-detail__list">
			<li v-for="row in rows" :key="row.name">
				<a href="#" class="activity-detail__link" @click.prevent="open_record(row)">
					{{ row_number(row) ? `${row_number(row)} — ` : "" }}{{ row.link_title || row.link_name }}
					<span v-if="row_current(row)" class="activity-links__current">({{ row_current(row) }})</span>
				</a>
				<div class="activity-links__meta">
					<StatusPill v-if="row_status(row)" :status="row_status(row)" />
					<span v-if="row.link_purpose" class="activity-links__purpose">{{ row.link_purpose }}</span>
					<button
						v-if="canWrite"
						type="button"
						class="btn btn-xs btn-default"
						@click="confirm_remove(row)"
					>
						{{ __("Remove") }}
					</button>
				</div>
			</li>
		</ul>
	</div>
</template>

<style scoped>
.activity-links__head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 10px;
}

.activity-links__current {
	color: var(--text-muted);
	font-weight: 400;
}

.activity-links__meta {
	display: flex;
	align-items: center;
	gap: 8px;
	flex: 0 0 auto;
}

.activity-links__purpose {
	font-size: var(--text-xs);
	color: var(--text-muted);
}
</style>
