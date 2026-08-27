<!-- One recursive node in ActivityOutlineView.vue's tree. Split into its own file because a
     `<script setup>` SFC can recursively reference itself in its own template (Vue auto-registers
     it under its filename for exactly this case) — a single file can't hold two independent
     recursive components the way an inline second <script> block might suggest. -->
<script setup>
import StatusPill from "./StatusPill.vue";

defineProps({
	node: { type: Object, required: true },
	collapsed: { type: Set, required: true },
});
const emit = defineEmits(["toggle", "open"]);

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}
</script>

<template>
	<div class="hub-outline__node">
		<div class="hub-outline__row" @click="emit('open', node.row.name)">
			<button
				v-if="node.children.length"
				type="button"
				class="hub-outline__toggle"
				:class="{ 'hub-outline__toggle--collapsed': collapsed.has(node.row.name) }"
				:aria-expanded="!collapsed.has(node.row.name)"
				@click.stop="emit('toggle', node.row.name)"
			>
				▾
			</button>
			<span v-else class="hub-outline__toggle-spacer" />
			<span class="hub-outline__code">{{ node.row.activity_code }}</span>
			<span class="hub-outline__name">{{ node.row.activity_name }}</span>
			<span v-if="node.row.is_group" class="indicator-pill gray">{{ __("Group") }}</span>
			<StatusPill :status="node.row.status" />
			<span class="hub-outline__date">{{ format_date(node.row.planned_end_date) }}</span>
			<span class="hub-outline__percent">{{ Math.round(node.row.percent_complete || 0) }}%</span>
		</div>
		<ul v-if="node.children.length && !collapsed.has(node.row.name)" class="hub-outline__children">
			<li v-for="child in node.children" :key="child.row.name" class="hub-outline__subtree">
				<ActivityOutlineNode :node="child" :collapsed="collapsed" @toggle="emit('toggle', $event)" @open="emit('open', $event)" />
			</li>
		</ul>
	</div>
</template>

<style scoped>
.hub-outline__children,
.hub-outline__subtree {
	list-style: none;
}

.hub-outline__children {
	margin: 0;
	padding-left: 22px;
	border-left: 1px solid var(--border-color);
	margin-left: 9px;
}

.hub-outline__row {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 7px 8px;
	border-radius: var(--border-radius);
	cursor: pointer;
}

.hub-outline__row:hover {
	background: var(--control-bg);
}

.hub-outline__toggle {
	appearance: none;
	border: none;
	background: none;
	padding: 0;
	width: 16px;
	height: 16px;
	line-height: 16px;
	text-align: center;
	color: var(--text-muted);
	cursor: pointer;
	font-size: var(--text-xs);
	transition: transform 0.1s ease;
	flex: 0 0 auto;
}

.hub-outline__toggle--collapsed {
	transform: rotate(-90deg);
}

.hub-outline__toggle-spacer {
	display: inline-block;
	width: 16px;
	flex: 0 0 auto;
}

.hub-outline__code {
	font-weight: 600;
	color: var(--text-color);
	flex: 0 0 auto;
}

.hub-outline__name {
	color: var(--text-color);
	flex: 1 1 auto;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.hub-outline__date {
	font-size: var(--text-xs);
	color: var(--text-muted);
	flex: 0 0 auto;
	min-width: 80px;
}

.hub-outline__percent {
	font-size: var(--text-xs);
	color: var(--text-muted);
	flex: 0 0 auto;
	min-width: 36px;
	text-align: right;
}
</style>
