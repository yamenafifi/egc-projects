<!-- Recursive tree row. <script setup> SFCs auto-register under their own filename, so this can
reference itself (WbsTreeNode) directly in the template for arbitrary tree depth.

Every rollup figure comes from the parent's already-fetched `get_wbs_summary` map — this
component never fetches its own data. It only ever DISPLAYS a number; nothing here computes or
stores one, matching api/wbs.py's own "derive, don't store" rule. -->
<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from "vue";
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

// Deliberate escape hatch for the "⋯" menu only — the code label itself opens the in-Hub Edit
// dialog (below), staying inside the Project Manager; this is for a System Manager/power user who
// specifically wants the raw native form.
function open_form() {
	frappe.set_route("Form", "EGC WBS Node", props.node.name);
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

// -- row actions: one "⋯" menu instead of four cramped icon-only buttons — a row here already
// carries name, discipline, two rollup metrics, a progress bar and a status pill; four more
// unlabeled targets was too dense to be legible. -------------------------------------------------

const menu_open = ref(null);
const menu_container = ref(null);

function toggle_menu() {
	menu_open.value = !menu_open.value;
}

function run(action) {
	menu_open.value = false;
	action();
}

function on_document_click(e) {
	if (menu_open.value && menu_container.value && !menu_container.value.contains(e.target)) {
		menu_open.value = false;
	}
}
onMounted(() => document.addEventListener("click", on_document_click));
onBeforeUnmount(() => document.removeEventListener("click", on_document_click));
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
			<span class="wbs-node__code hub-link" @click="canWrite ? emit('edit', node) : open_form()">{{ node.wbs_code }}</span>
			<span class="wbs-node__name">{{ node.wbs_name }}</span>
			<span class="wbs-node__discipline">{{ node.discipline || "—" }}</span>

			<span v-if="summary" class="wbs-node__metric">
				{{ __("{0}/{1} activities", [summary.activity_completed, summary.activity_total]) }}
			</span>
			<span v-if="summary && summary.activity_total" class="wbs-node__progress">
				<span class="wbs-node__progress-track">
					<span class="wbs-node__progress-fill" :style="{ width: (summary.activity_progress || 0) + '%' }" />
				</span>
			</span>
			<span v-else class="wbs-node__progress" />
			<span v-if="summary && summary.activity_overdue_count" class="wbs-node__overdue">
				{{ __("{0} overdue", [summary.activity_overdue_count]) }}
			</span>
			<span v-if="summary" class="wbs-node__metric">
				{{ __("{0} docs · {1} open submittals", [summary.document_count, summary.submittal_open_count]) }}
			</span>
			<span v-if="summary && (summary.planned_start || summary.planned_finish)" class="wbs-node__dates">
				{{ format_date(summary.planned_start) }} – {{ format_date(summary.planned_finish) }}
			</span>

			<StatusPill :status="node.status" />

			<span v-if="canWrite" ref="menu_container" class="wbs-node__menu">
				<button type="button" class="wbs-node__menu-trigger" :title="__('Actions')" @click.stop="toggle_menu">
					⋯
				</button>
				<div v-if="menu_open" class="wbs-node__menu-dropdown" role="menu">
					<button type="button" role="menuitem" @click.stop="run(() => emit('edit', node))">
						{{ __("Edit") }}
					</button>
					<button type="button" role="menuitem" @click.stop="run(() => emit('quick-add', node))">
						{{ __("Add Child") }}
					</button>
					<button
						type="button"
						role="menuitem"
						:disabled="siblingIndex === 0"
						@click.stop="run(() => emit('move', node, -1))"
					>
						{{ __("Move Up") }}
					</button>
					<button
						type="button"
						role="menuitem"
						:disabled="siblingIndex === siblingCount - 1"
						@click.stop="run(() => emit('move', node, 1))"
					>
						{{ __("Move Down") }}
					</button>
					<button type="button" role="menuitem" @click.stop="run(open_form)">
						{{ __("View Raw Record ↗") }}
					</button>
				</div>
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

.wbs-node__menu {
	position: relative;
	flex: 0 0 auto;
}

.wbs-node__menu-trigger {
	appearance: none;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	color: var(--text-muted);
	width: 22px;
	height: 22px;
	line-height: 1;
	font-size: 13px;
	cursor: pointer;
}

.wbs-node__menu-trigger:hover {
	color: var(--text-color);
	background: var(--control-bg);
}

.wbs-node__menu-dropdown {
	position: absolute;
	top: calc(100% + 4px);
	right: 0;
	z-index: 10;
	min-width: 130px;
	display: flex;
	flex-direction: column;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	background: var(--fg-color);
	box-shadow: var(--shadow-lg, 0 4px 16px rgba(0, 0, 0, 0.12));
	padding: 4px;
}

.wbs-node__menu-dropdown button {
	appearance: none;
	background: none;
	border: none;
	text-align: left;
	padding: 6px 10px;
	font-size: var(--text-sm);
	color: var(--text-color);
	border-radius: var(--border-radius);
	cursor: pointer;
}

.wbs-node__menu-dropdown button:hover:not(:disabled) {
	background: var(--control-bg);
}

.wbs-node__menu-dropdown button:disabled {
	opacity: 0.35;
	cursor: default;
}
</style>
