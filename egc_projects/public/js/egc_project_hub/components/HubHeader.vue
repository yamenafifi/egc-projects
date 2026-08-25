<script setup>
import { ref } from "vue";
import StatusPill from "./StatusPill.vue";
import ProjectLinkControl from "./ProjectLinkControl.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
	loading: { type: Boolean, default: false },
});
const emit = defineEmits(["switch-project"]);

const switching = ref(false);

function on_switch(value) {
	// Deferred to a macrotask: this fires from inside Frappe's own Link control change
	// handler, which keeps running its own async validation after calling ours. Unmounting
	// ProjectLinkControl's DOM synchronously here races that in-flight work and throws inside
	// Frappe's control code. A setTimeout(0) lets that finish before we tear the control down.
	setTimeout(() => {
		switching.value = false;
	}, 0);
	if (value && value !== props.project) emit("switch-project", value);
}

function open_form() {
	frappe.set_route("Form", "Project", props.project);
}

function format_date_range(dates) {
	if (!dates) return "";
	const { expected_start_date, expected_end_date } = dates;
	if (!expected_start_date && !expected_end_date) return "";
	const start = expected_start_date ? frappe.datetime.str_to_user(expected_start_date) : "?";
	const end = expected_end_date ? frappe.datetime.str_to_user(expected_end_date) : "?";
	return `${start} – ${end}`;
}
</script>

<template>
	<div class="hub-header">
		<div class="hub-header__identity">
			<div class="hub-header__title-row">
				<a class="hub-header__project" href="#" @click.prevent="open_form">{{ project }}</a>
				<StatusPill v-if="context" :status="context.status" />
			</div>
			<div v-if="context" class="hub-header__meta">
				<span class="hub-header__project-name">{{ context.project_name }}</span>
				<span v-if="context.customer" class="hub-header__sep">·</span>
				<span v-if="context.customer">{{ context.customer }}</span>
				<span v-if="format_date_range(context.dates)" class="hub-header__sep">·</span>
				<span>{{ format_date_range(context.dates) }}</span>
			</div>
			<div v-else-if="loading" class="hub-header__meta hub-header__meta--loading">{{ __("Loading…") }}</div>
		</div>

		<div class="hub-header__complete" v-if="context && context.percent_complete !== null && context.percent_complete !== undefined">
			<div class="hub-header__complete-label">{{ __("Complete") }}</div>
			<div class="hub-header__progress">
				<div class="hub-header__progress-bar" :style="{ width: (context.percent_complete || 0) + '%' }" />
			</div>
			<div class="hub-header__complete-value">{{ Math.round(context.percent_complete || 0) }}%</div>
		</div>

		<div class="hub-header__switch">
			<button
				v-if="!switching"
				class="btn btn-sm btn-default"
				@click="switching = true"
			>
				{{ __("Switch Project") }}
			</button>
			<ProjectLinkControl
				v-else
				:model-value="project"
				:placeholder="__('Search projects…')"
				@update:model-value="on_switch"
			/>
		</div>
	</div>
</template>

<style scoped>
.hub-header {
	display: flex;
	align-items: center;
	gap: 20px;
	padding: 14px 18px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	background: var(--fg-color);
	margin-bottom: 14px;
	flex-wrap: wrap;
}

.hub-header__identity {
	flex: 1 1 260px;
	min-width: 220px;
}

.hub-header__title-row {
	display: flex;
	align-items: center;
	gap: 10px;
}

.hub-header__project {
	font-size: var(--text-lg);
	font-weight: 600;
	color: var(--text-color);
}

.hub-header__project:hover {
	color: var(--text-color);
	text-decoration: underline;
}

.hub-header__meta {
	margin-top: 4px;
	font-size: var(--text-sm);
	color: var(--text-muted);
}

.hub-header__meta--loading {
	font-style: italic;
}

.hub-header__sep {
	margin: 0 6px;
}

.hub-header__complete {
	display: flex;
	align-items: center;
	gap: 8px;
	flex: 0 0 220px;
}

.hub-header__complete-label {
	font-size: var(--text-xs);
	color: var(--text-muted);
	white-space: nowrap;
}

.hub-header__progress {
	flex: 1;
	height: 6px;
	border-radius: var(--border-radius-full);
	background: var(--control-bg);
	overflow: hidden;
}

.hub-header__progress-bar {
	height: 100%;
	background: var(--dark-green-500, var(--green-500));
	border-radius: var(--border-radius-full);
}

.hub-header__complete-value {
	font-size: var(--text-xs);
	color: var(--text-muted);
	width: 34px;
	text-align: right;
}

.hub-header__switch {
	flex: 0 0 auto;
}
</style>
