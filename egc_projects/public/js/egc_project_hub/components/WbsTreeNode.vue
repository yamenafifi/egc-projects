<!-- Recursive tree row. <script setup> SFCs auto-register under their own filename, so this can
reference itself (WbsTreeNode) directly in the template for arbitrary tree depth. -->
<script setup>
import { ref, computed } from "vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps({
	node: { type: Object, required: true },
	childrenByParent: { type: Object, required: true },
	depth: { type: Number, default: 0 },
});

const expanded = ref(props.depth < 1);

const children = computed(() => props.childrenByParent[props.node.name] || []);
const has_children = computed(() => children.value.length > 0);

function open_form() {
	frappe.set_route("Form", "EGC WBS Node", props.node.name);
}
</script>

<template>
	<div class="wbs-node">
		<div class="wbs-node__row" :style="{ paddingLeft: depth * 20 + 'px' }">
			<span
				class="wbs-node__toggle"
				:class="{ 'wbs-node__toggle--empty': !has_children }"
				@click="has_children && (expanded = !expanded)"
			>
				<template v-if="has_children">{{ expanded ? "▾" : "▸" }}</template>
			</span>
			<span class="wbs-node__code hub-link" @click="open_form">{{ node.wbs_code }}</span>
			<span class="wbs-node__name">{{ node.wbs_name }}</span>
			<span class="wbs-node__discipline">{{ node.discipline || "—" }}</span>
			<StatusPill :status="node.status" />
		</div>
		<div v-if="has_children && expanded" class="wbs-node__children">
			<WbsTreeNode
				v-for="child in children"
				:key="child.name"
				:node="child"
				:children-by-parent="childrenByParent"
				:depth="depth + 1"
			/>
		</div>
	</div>
</template>

<style scoped>
.wbs-node__row {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 7px 10px;
	border-bottom: 1px solid var(--border-color);
	font-size: var(--text-sm);
}

.wbs-node:last-child > .wbs-node__row {
	border-bottom: none;
}

.wbs-node__toggle {
	width: 16px;
	flex: 0 0 auto;
	text-align: center;
	color: var(--text-muted);
	cursor: pointer;
	user-select: none;
}

.wbs-node__toggle--empty {
	cursor: default;
}

.wbs-node__code.hub-link {
	color: var(--text-color);
	font-weight: 500;
	cursor: pointer;
	flex: 0 0 auto;
}

.wbs-node__code.hub-link:hover {
	text-decoration: underline;
}

.wbs-node__name {
	flex: 1;
	color: var(--text-color);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.wbs-node__discipline {
	flex: 0 0 90px;
	color: var(--text-muted);
	font-size: var(--text-xs);
}
</style>
