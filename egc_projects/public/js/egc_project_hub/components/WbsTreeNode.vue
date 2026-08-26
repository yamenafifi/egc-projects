<!-- Recursive tree row. <script setup> SFCs auto-register under their own filename, so this can
reference itself (WbsTreeNode) directly in the template for arbitrary tree depth.

Every rollup figure comes from the parent's already-fetched `get_wbs_summary` map — this
component never fetches its own data. It only ever DISPLAYS a number; nothing here computes or
stores one, matching api/wbs.py's own "derive, don't store" rule. -->
<script setup>
import { ref, computed } from "vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps({
	node: { type: Object, required: true },
	childrenByParent: { type: Object, required: true },
	summaryByName: { type: Object, default: () => ({}) },
	depth: { type: Number, default: 0 },
	canWrite: { type: Boolean, default: false },
	siblingCount: { type: Number, default: 1 },
	siblingIndex: { type: Number, default: 0 },
});
const emit = defineEmits(["move", "quick-add", "edit"]);

const expanded = ref(props.depth < 1);

const children = computed(() => props.childrenByParent[props.node.name] || []);
const has_children = computed(() => children.value.length > 0);
const summary = computed(() => props.summaryByName[props.node.name] || null);

function open_form() {
	frappe.set_route("Form", "EGC WBS Node", props.node.name);
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
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

			<span v-if="summary" class="wbs-node__metric" :title="__('Activities')">
				{{ summary.activity_completed }}/{{ summary.activity_total }}
			</span>
			<span v-if="summary && summary.activity_total" class="wbs-node__progress">
				<span class="wbs-node__progress-track">
					<span class="wbs-node__progress-fill" :style="{ width: (summary.activity_progress || 0) + '%' }" />
				</span>
			</span>
			<span v-else class="wbs-node__progress" />
			<span v-if="summary && summary.activity_overdue_count" class="wbs-node__overdue" :title="__('Overdue activities')">
				{{ summary.activity_overdue_count }} {{ __("overdue") }}
			</span>
			<span v-if="summary" class="wbs-node__metric" :title="__('Drawings / Open Submittals')">
				{{ summary.drawing_count }}📄 {{ summary.submittal_open_count }}📝
			</span>
			<span v-if="summary && (summary.planned_start || summary.planned_finish)" class="wbs-node__dates">
				{{ format_date(summary.planned_start) }} – {{ format_date(summary.planned_finish) }}
			</span>

			<StatusPill :status="node.status" />

			<span v-if="canWrite" class="wbs-node__actions">
				<button
					type="button"
					class="wbs-node__action-btn"
					:disabled="siblingIndex === 0"
					:title="__('Move up')"
					@click.stop="emit('move', node, -1)"
				>
					↑
				</button>
				<button
					type="button"
					class="wbs-node__action-btn"
					:disabled="siblingIndex === siblingCount - 1"
					:title="__('Move down')"
					@click.stop="emit('move', node, 1)"
				>
					↓
				</button>
				<button type="button" class="wbs-node__action-btn" :title="__('Edit')" @click.stop="emit('edit', node)">
					✎
				</button>
				<button
					type="button"
					class="wbs-node__action-btn"
					:title="__('Add child')"
					@click.stop="emit('quick-add', node)"
				>
					+
				</button>
			</span>
		</div>
		<div v-if="has_children && expanded" class="wbs-node__children">
			<WbsTreeNode
				v-for="(child, index) in children"
				:key="child.name"
				:node="child"
				:children-by-parent="childrenByParent"
				:summary-by-name="summaryByName"
				:depth="depth + 1"
				:can-write="canWrite"
				:sibling-count="children.length"
				:sibling-index="index"
				@move="(...args) => emit('move', ...args)"
				@quick-add="(...args) => emit('quick-add', ...args)"
				@edit="(...args) => emit('edit', ...args)"
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
	white-space: nowrap;
}

.wbs-node__code.hub-link:hover {
	text-decoration: underline;
}

.wbs-node__name {
	flex: 1 1 160px;
	min-width: 100px;
	color: var(--text-color);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.wbs-node__discipline {
	flex: 0 0 70px;
	color: var(--text-muted);
	font-size: var(--text-xs);
}

.wbs-node__metric {
	flex: 0 0 auto;
	font-size: var(--text-xs);
	color: var(--text-muted);
	white-space: nowrap;
}

.wbs-node__progress {
	flex: 0 0 60px;
}

.wbs-node__progress-track {
	display: block;
	height: 6px;
	border-radius: var(--border-radius-full);
	background: var(--control-bg);
	overflow: hidden;
}

.wbs-node__progress-fill {
	display: block;
	height: 100%;
	background: var(--dark-green-500, var(--green-500));
}

.wbs-node__overdue {
	flex: 0 0 auto;
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--red-500, var(--text-on-red));
	white-space: nowrap;
}

.wbs-node__dates {
	flex: 0 0 auto;
	font-size: var(--text-xs);
	color: var(--text-muted);
	white-space: nowrap;
}

.wbs-node__actions {
	flex: 0 0 auto;
	display: flex;
	gap: 2px;
}

.wbs-node__action-btn {
	appearance: none;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	color: var(--text-muted);
	width: 22px;
	height: 22px;
	line-height: 1;
	font-size: 11px;
	cursor: pointer;
}

.wbs-node__action-btn:hover:not(:disabled) {
	color: var(--text-color);
	background: var(--control-bg);
}

.wbs-node__action-btn:disabled {
	opacity: 0.35;
	cursor: default;
}
</style>
