<!-- WBS Node detail drawer — same right-hand overlay shell as ActivityDetail.vue/DocumentDetail.vue
(class prefix renamed wbs-detail__*), opened as a genuine "view" surface instead of dropping
straight into the Edit dialog: clicking a WBS row's code/name now reads it first, with "Edit" as
its own explicit action inside here. Every field it shows comes straight off the row object
WbsTab.vue already has from get_wbs_summary — no second network round trip. -->
<script setup>
import { computed } from "vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps({
	node: { type: Object, required: true },
	summaryByName: { type: Object, default: () => ({}) },
	canWrite: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "edit", "quick-add"]);

function open_form() {
	frappe.set_route("Form", "EGC WBS Node", props.node.name);
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

// Ancestors, root first — walks `parent` links through the already-fetched summary map, no
// extra fetch needed.
const breadcrumb = computed(() => {
	const trail = [];
	let current = props.summaryByName[props.node.parent];
	while (current) {
		trail.unshift(current);
		current = props.summaryByName[current.parent];
	}
	return trail;
});

const children = computed(() =>
	Object.values(props.summaryByName).filter((n) => n.parent === props.node.name)
);
</script>

<template>
	<div class="wbs-detail__backdrop" @click.self="$emit('close')">
		<div class="wbs-detail__panel" role="dialog" aria-modal="true">
			<div class="wbs-detail__header">
				<div class="wbs-detail__identity">
					<nav v-if="breadcrumb.length" class="wbs-detail__breadcrumb">
						<span v-for="a in breadcrumb" :key="a.name">{{ a.wbs_name }} / </span>
					</nav>
					<div class="wbs-detail__code">{{ node.wbs_code }}</div>
					<div class="wbs-detail__name">{{ node.wbs_name }}</div>
				</div>
				<div class="wbs-detail__header-actions">
					<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="emit('edit', node)">
						{{ __("Edit") }}
					</button>
					<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="emit('quick-add', node)">
						{{ __("Add Child") }}
					</button>
					<a href="#" class="hub-link" @click.prevent="open_form">{{ __("Open Form ↗") }}</a>
					<button type="button" class="wbs-detail__close" :aria-label="__('Close')" @click="$emit('close')">
						×
					</button>
				</div>
			</div>

			<div class="wbs-detail__body">
				<section class="wbs-detail__section">
					<div class="wbs-detail__status-row">
						<StatusPill :status="node.status" />
						<span v-if="node.discipline" class="wbs-detail__discipline">{{ node.discipline }}</span>
						<span v-if="node.is_group" class="wbs-detail__group-tag">{{ __("Group") }}</span>
					</div>

					<p v-if="node.description" class="wbs-detail__description">{{ node.description }}</p>
					<p v-else class="wbs-detail__no-description">{{ __("No description yet.") }}</p>
				</section>

				<section class="wbs-detail__section">
					<div class="wbs-detail__section-title">{{ __("Schedule & Progress") }}</div>
					<dl class="wbs-detail__meta">
						<div>
							<dt>{{ __("Planned Start") }}</dt>
							<dd>{{ format_date(node.planned_start) }}</dd>
						</div>
						<div>
							<dt>{{ __("Planned Finish") }}</dt>
							<dd>{{ format_date(node.planned_finish) }}</dd>
						</div>
						<div>
							<dt>{{ __("Activities") }}</dt>
							<dd>{{ __("{0}/{1} complete", [node.activity_completed || 0, node.activity_total || 0]) }}</dd>
						</div>
						<div>
							<dt>{{ __("Overdue") }}</dt>
							<dd>{{ node.activity_overdue_count || 0 }}</dd>
						</div>
					</dl>
				</section>

				<section class="wbs-detail__section">
					<div class="wbs-detail__section-title">{{ __("Documents & Submittals") }}</div>
					<dl class="wbs-detail__meta">
						<div>
							<dt>{{ __("Documents") }}</dt>
							<dd>{{ node.document_count || 0 }}</dd>
						</div>
						<div>
							<dt>{{ __("Drawings") }}</dt>
							<dd>{{ node.drawing_count || 0 }}</dd>
						</div>
						<div>
							<dt>{{ __("Open Submittals") }}</dt>
							<dd>{{ node.submittal_open_count || 0 }}</dd>
						</div>
						<div>
							<dt>{{ __("Overdue Submittals") }}</dt>
							<dd>{{ node.submittal_overdue_count || 0 }}</dd>
						</div>
					</dl>
				</section>

				<section v-if="children.length" class="wbs-detail__section">
					<div class="wbs-detail__section-title">{{ __("Child Nodes") }}</div>
					<ul class="wbs-detail__list">
						<li v-for="child in children" :key="child.name">
							<span class="wbs-detail__child-code">{{ child.wbs_code }}</span>
							{{ child.wbs_name }}
						</li>
					</ul>
				</section>
			</div>
		</div>
	</div>
</template>

<style scoped>
.wbs-detail__backdrop {
	position: fixed;
	inset: 0;
	background: rgba(0, 0, 0, 0.35);
	z-index: 500;
	display: flex;
	justify-content: flex-end;
}

.wbs-detail__panel {
	width: min(560px, 100vw);
	max-width: 100vw;
	height: 100vh;
	background: var(--fg-color);
	border-left: 1px solid var(--border-color);
	box-shadow: var(--shadow-lg, -4px 0 24px rgba(0, 0, 0, 0.2));
	display: flex;
	flex-direction: column;
	overflow: hidden;
}

.wbs-detail__header {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 10px;
	padding: 16px 18px;
	border-bottom: 1px solid var(--border-color);
	flex: 0 0 auto;
}

.wbs-detail__breadcrumb {
	font-size: var(--text-xs);
	color: var(--text-muted);
	margin-bottom: 2px;
}

.wbs-detail__code {
	font-size: var(--text-md);
	font-weight: 600;
	color: var(--text-color);
}

.wbs-detail__name {
	font-size: var(--text-sm);
	color: var(--text-muted);
	margin-top: 2px;
}

.wbs-detail__header-actions {
	display: flex;
	align-items: center;
	gap: 12px;
	flex: 0 0 auto;
	white-space: nowrap;
}

.wbs-detail__close {
	appearance: none;
	border: none;
	background: none;
	font-size: 22px;
	line-height: 1;
	color: var(--text-muted);
	cursor: pointer;
	padding: 2px 4px;
}

.wbs-detail__close:hover {
	color: var(--text-color);
}

.wbs-detail__body {
	flex: 1 1 auto;
	overflow-y: auto;
	padding: 18px;
	display: flex;
	flex-direction: column;
	gap: 22px;
}

.wbs-detail__section-title {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
	margin-bottom: 10px;
}

.wbs-detail__status-row {
	display: flex;
	align-items: center;
	gap: 8px;
	margin-bottom: 12px;
}

.wbs-detail__discipline {
	font-size: var(--text-xs);
	color: var(--text-muted);
	background: var(--control-bg);
	border-radius: var(--border-radius);
	padding: 2px 8px;
}

.wbs-detail__group-tag {
	font-size: var(--text-xs);
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
}

.wbs-detail__description {
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: pre-wrap;
	margin: 0;
}

.wbs-detail__no-description {
	font-size: var(--text-sm);
	color: var(--text-muted);
	font-style: italic;
	margin: 0;
}

.wbs-detail__meta {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
	gap: 10px 16px;
	margin: 0;
}

.wbs-detail__meta dt {
	font-size: var(--text-xs);
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
}

.wbs-detail__meta dd {
	margin: 2px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
}

.wbs-detail__list {
	list-style: none;
	margin: 0;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 6px;
	font-size: var(--text-sm);
	color: var(--text-color);
}

.wbs-detail__child-code {
	font-weight: 500;
	margin-right: 6px;
}
</style>
