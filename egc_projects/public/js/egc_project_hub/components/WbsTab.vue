<script setup>
import { computed, watch } from "vue";
import {
	get_wbs_summary,
	reorder_wbs_nodes,
	copy_wbs_branch,
	bulk_create_wbs_nodes,
	create_wbs_node,
	create_child_wbs_node,
	update_wbs_node,
} from "./wbs_api";
import { useHubResource } from "../composables/useHubResource";
import { openExportDialog, openImportDialog } from "./bulk_transfer_flow";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import WbsTreeNode from "./WbsTreeNode.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { data, loading, error, reload } = useHubResource(() => get_wbs_summary(props.project));
watch(() => props.project, reload, { immediate: true });

// A client-side hint only — api/wbs.py's own permission checks are the actual boundary, same
// discipline as every write action elsewhere in this Hub.
const WRITE_ROLES = ["EGC Project Manager", "EGC Project Engineer", "System Manager"];
const can_write = computed(() => (frappe.user_roles || []).some((role) => WRITE_ROLES.includes(role)));

const summary_by_name = computed(() => {
	const map = {};
	for (const node of data.value || []) map[node.name] = node;
	return map;
});

const children_by_parent = computed(() => {
	const map = {};
	for (const node of data.value || []) {
		const key = node.parent || "";
		(map[key] = map[key] || []).push(node);
	}
	for (const key of Object.keys(map)) {
		map[key].sort((a, b) => (a.sequence || 0) - (b.sequence || 0));
	}
	return map;
});

const roots = computed(() => children_by_parent.value[""] || []);

function open_tree_view() {
	frappe.set_route("Tree", "EGC WBS Node", { project: props.project });
}

function open_export_dialog() {
	openExportDialog({ project: props.project, doctype: "EGC WBS Node", label: __("WBS Nodes") });
}

function open_import_dialog() {
	openImportDialog({
		project: props.project,
		doctype: "EGC WBS Node",
		label: __("WBS Nodes"),
		onImported: reload,
	});
}

function create_root() {
	// Same in-Hub dialog as the per-row "Add Child WBS Node" quick-add (on_quick_add below),
	// just without a parent — stays inside the Hub instead of navigating to the native form.
	const dialog = new frappe.ui.Dialog({
		title: __("New WBS Node"),
		fields: [
			{ fieldname: "wbs_code", fieldtype: "Data", label: __("WBS Code"), reqd: 1 },
			{ fieldname: "wbs_name", fieldtype: "Data", label: __("WBS Name"), reqd: 1 },
			{ fieldname: "is_group", fieldtype: "Check", label: __("Is Group") },
			{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline" },
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			create_wbs_node({ ...values, project: props.project })
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Create WBS Node"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

// -- reorder (up/down within siblings) ---------------------------------------------------------

async function on_move(node, direction) {
	const siblings = children_by_parent.value[node.parent || ""] || [];
	const index = siblings.findIndex((n) => n.name === node.name);
	const swap_index = index + direction;
	if (swap_index < 0 || swap_index >= siblings.length) return;

	const ordered = [...siblings];
	[ordered[index], ordered[swap_index]] = [ordered[swap_index], ordered[index]];

	try {
		await reorder_wbs_nodes(node.parent || null, ordered.map((n) => n.name));
		reload();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Reorder"), message: e.message, indicator: "red" });
	}
}

// -- quick add child ------------------------------------------------------------------------

function on_quick_add(node) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Child WBS Node"),
		fields: [
			{ fieldname: "wbs_code", fieldtype: "Data", label: __("WBS Code"), reqd: 1 },
			{ fieldname: "wbs_name", fieldtype: "Data", label: __("WBS Name"), reqd: 1 },
			{ fieldname: "is_group", fieldtype: "Check", label: __("Is Group") },
			{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline", default: node.discipline },
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			// Not create_wbs_node — that's a bare frappe.client.insert and this node may not be
			// a group yet. create_child_wbs_node makes it one first, same as create_child_activity
			// does for Activities: "Add Child" always implies the parent becomes a group.
			create_child_wbs_node(node.name, props.project, values)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Create WBS Node"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

// -- inline edit ------------------------------------------------------------------------------

function on_edit(node) {
	const dialog = new frappe.ui.Dialog({
		title: __("Edit WBS Node"),
		fields: [
			{ fieldname: "wbs_name", fieldtype: "Data", label: __("WBS Name"), default: node.wbs_name, reqd: 1 },
			{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline", default: node.discipline },
			{ fieldname: "status", fieldtype: "Select", label: __("Status"), options: ["Active", "On Hold", "Completed", "Cancelled"], default: node.status },
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			update_wbs_node(node.name, values)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Save"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

// -- copy branch ------------------------------------------------------------------------------

function open_copy_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Copy WBS Branch"),
		fields: [
			{
				fieldname: "source_node",
				fieldtype: "Link",
				label: __("Branch to Copy"),
				options: "EGC WBS Node",
				reqd: 1,
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "target_project",
				fieldtype: "Link",
				label: __("Target Project"),
				options: "Project",
				default: props.project,
				description: __("Leave as this project to copy within it, or choose another project to reuse this branch as a template."),
			},
			{
				fieldname: "target_parent",
				fieldtype: "Link",
				label: __("Target Parent (optional)"),
				options: "EGC WBS Node",
				get_query: () => ({ filters: { project: dialog.get_value("target_project") || props.project } }),
			},
		],
		primary_action_label: __("Copy"),
		primary_action(values) {
			copy_wbs_branch(values.source_node, values.target_parent || null, values.target_project || props.project)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Copy Branch"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

// -- bulk create ------------------------------------------------------------------------------
// Matches ERPNext's own "Add Multiple Tasks" dialog (erpnext/projects/doctype/task/
// task_tree.js) — an in-place-editable Table field inside a plain frappe.ui.Dialog, rather than
// a hand-rolled Vue modal, so this looks and behaves like every other multi-row entry point in
// Frappe/ERPNext, complete with its native add/remove-row affordances.

function open_bulk_dialog() {
	const rows = [];
	const dialog = new frappe.ui.Dialog({
		title: __("Bulk Add WBS Nodes"),
		fields: [
			{
				fieldname: "parent_egc_wbs_node",
				fieldtype: "Link",
				label: __("Parent (optional — leave blank for root nodes)"),
				options: "EGC WBS Node",
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "rows",
				fieldtype: "Table",
				in_place_edit: true,
				data: rows,
				get_data: () => rows,
				fields: [
					{ fieldtype: "Data", fieldname: "wbs_code", in_list_view: 1, reqd: 1, label: __("Code") },
					{ fieldtype: "Data", fieldname: "wbs_name", in_list_view: 1, reqd: 1, label: __("Name") },
					{ fieldtype: "Check", fieldname: "is_group", in_list_view: 1, label: __("Group") },
					{ fieldtype: "Link", fieldname: "discipline", in_list_view: 1, options: "EGC Discipline", label: __("Discipline") },
				],
			},
		],
		primary_action_label: __("Create All"),
		primary_action(values) {
			const data = (dialog.get_values().rows || []).filter((r) => r.wbs_code && r.wbs_name);
			if (!data.length) {
				frappe.msgprint(__("Add at least one row with a Code and a Name."));
				return;
			}
			bulk_create_wbs_nodes(values.parent_egc_wbs_node || null, props.project, data)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Bulk Create"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}
</script>

<template>
	<div class="hub-wbs">
		<LoadingState v-if="loading" :rows="6" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />
		<EmptyState
			v-else-if="!roots.length"
			:title="__('No WBS nodes yet')"
			:description="__('Break this project down into a work breakdown structure to organise activities and documents.')"
			:action-label="__('Add WBS Node')"
			@action="create_root"
		/>

		<template v-else>
			<div class="hub-toolbar">
				<span class="hub-wbs__spacer" />
				<button v-if="can_write" type="button" class="btn btn-xs btn-default" @click="open_copy_dialog">
					{{ __("Copy Branch") }}
				</button>
				<button v-if="can_write" type="button" class="btn btn-xs btn-default" @click="open_bulk_dialog">
					{{ __("Bulk Add") }}
				</button>
				<button type="button" class="btn btn-xs btn-default" @click="open_export_dialog">
					{{ __("Export") }}
				</button>
				<button v-if="can_write" type="button" class="btn btn-xs btn-default" @click="open_import_dialog">
					{{ __("Import") }}
				</button>
				<button v-if="can_write" type="button" class="btn btn-sm btn-primary" @click="create_root">
					{{ __("+ New WBS Node") }}
				</button>
				<a href="#" class="hub-link" @click.prevent="open_tree_view">{{ __("Open Tree View") }}</a>
			</div>

			<div class="hub-table-wrap hub-wbs__tree">
				<WbsTreeNode
					v-for="(root, index) in roots"
					:key="root.name"
					:node="root"
					:children-by-parent="children_by_parent"
					:summary-by-name="summary_by_name"
					:can-write="can_write"
					:sibling-count="roots.length"
					:sibling-index="index"
					@move="on_move"
					@quick-add="on_quick_add"
					@edit="on_edit"
				/>
			</div>
		</template>
	</div>
</template>

<style scoped>
.hub-wbs__tree {
	overflow-x: auto;
}

.hub-wbs__spacer {
	flex: 1;
}
</style>
