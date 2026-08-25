<script setup>
import { computed, watch } from "vue";
import { get_wbs_tree } from "../api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import WbsTreeNode from "./WbsTreeNode.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { data, loading, error, reload } = useHubResource(() => get_wbs_tree(props.project));
watch(() => props.project, reload, { immediate: true });

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
</script>

<template>
	<div class="hub-wbs">
		<LoadingState v-if="loading" :rows="6" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />
		<EmptyState
			v-else-if="!roots.length"
			:title="__('No WBS nodes yet')"
			:description="__('Break this project down into a work breakdown structure to organise activities and documents.')"
			:action-label="__('Open WBS Tree')"
			@action="open_tree_view"
		/>
		<div v-else class="hub-table-wrap hub-wbs__tree">
			<WbsTreeNode v-for="root in roots" :key="root.name" :node="root" :children-by-parent="children_by_parent" />
		</div>
	</div>
</template>

<style scoped>
.hub-wbs__tree {
	overflow-x: auto;
}
</style>
