<!-- Outline view (Level 0 §27-§28's [Table] [Gantt] [Outline] switch) — a genuine collapsible
     tree, which the Table view deliberately isn't: Table shows every row flat with indentation as
     a visual hint only (`row.indent`, from api/hub.py's get_activities), useful for scanning and
     filtering the whole register at once. Outline is for the opposite job — collapsing a group
     hides everything under it, so a PM can focus on one branch of a large breakdown without the
     rest of the tree crowding it out. Builds its tree client-side from the SAME `rows` prop
     ActivitiesTab.vue already has loaded (via `parent_egc_activity`) — no separate server call. -->
<script setup>
import { computed, ref } from "vue";
import ActivityOutlineNode from "./ActivityOutlineNode.vue";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
	rows: { type: Array, default: () => [] },
});
const emit = defineEmits(["open-activity"]);

const collapsed = ref(new Set());

function toggle(name) {
	const next = new Set(collapsed.value);
	if (next.has(name)) {
		next.delete(name);
	} else {
		next.add(name);
	}
	collapsed.value = next;
}

function open(name) {
	emit("open-activity", name);
}

const tree = computed(() => {
	const by_parent = new Map();
	for (const row of props.rows) {
		const key = row.parent_egc_activity || "";
		if (!by_parent.has(key)) by_parent.set(key, []);
		by_parent.get(key).push(row);
	}
	for (const list of by_parent.values()) {
		list.sort(
			(a, b) => (a.sequence || 0) - (b.sequence || 0) || (a.activity_code || "").localeCompare(b.activity_code || "")
		);
	}

	function build(parent_key) {
		return (by_parent.get(parent_key) || []).map((row) => ({ row, children: build(row.name) }));
	}

	const roots = build("");
	// A row whose OWN parent isn't in the current (filtered) row set is treated as a root too —
	// otherwise a search/filter that matches a child but not its parent would make that child
	// vanish entirely instead of surfacing at the top level.
	const present = new Set(props.rows.map((r) => r.name));
	for (const row of props.rows) {
		if (row.parent_egc_activity && !present.has(row.parent_egc_activity)) {
			roots.push({ row, children: build(row.name) });
		}
	}
	return roots;
});
</script>

<template>
	<div class="hub-outline">
		<EmptyState v-if="!tree.length" :title="__('No activities to show')" />
		<ul v-else class="hub-outline__list">
			<li v-for="node in tree" :key="node.row.name" class="hub-outline__subtree">
				<ActivityOutlineNode :node="node" :collapsed="collapsed" @toggle="toggle" @open="open" />
			</li>
		</ul>
	</div>
</template>

<style scoped>
.hub-outline__list,
.hub-outline__subtree {
	list-style: none;
	margin: 0;
	padding: 0;
}
</style>
