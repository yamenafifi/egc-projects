<!-- Gantt view (Level 0 §27-§28's [Table] [Gantt] [Outline] switch). Uses Frappe's OWN bundled
     frappe-gantt library (the same one core's native Gantt list-view uses), loaded at runtime via
     `frappe.require` — not bundled into egc_projects' own esbuild output, so this view costs
     nothing until a user actually opens it, and never drifts from whatever frappe-gantt version
     core itself ships.

     View-only: dragging a bar is a frappe-gantt built-in (this version has no `readonly` option),
     but nothing here listens for `on_date_change`/`on_progress_change`, so a drag never persists
     — it just snaps back on the next reload. Real rescheduling happens through the Activity
     detail drawer (or a predecessor's own dates, which schedule_engine.py then propagates
     forward automatically). A single click on a bar is this library's own trigger for its built-in
     info popup (`popup_trigger`) — `on_click` only fires on DOUBLE-click (`setup_click_event` in
     frappe-gantt itself), which is why opening the Activity drawer from here is a double-click,
     not a single one; the toolbar hint below says so rather than leaving it to be discovered. -->
<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from "vue";
import { get_activity_gantt_rows } from "./activities_api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
	project: { type: String, required: true },
});
const emit = defineEmits(["open-activity"]);

const { data, loading, error, reload } = useHubResource(() => get_activity_gantt_rows(props.project));

const container = ref(null);
const view_mode = ref("Week");
const VIEW_MODES = ["Day", "Week", "Month"];

let gantt_instance = null;
let libs_ready = false;

async function ensure_libs() {
	if (libs_ready) return;
	await frappe.require([
		"assets/frappe/node_modules/frappe-gantt/dist/frappe-gantt.css",
		"assets/frappe/node_modules/frappe-gantt/dist/frappe-gantt.min.js",
	]);
	libs_ready = true;
}

// frappe-gantt throws on a task with no `start`/`end` at all — Activities with no planned dates
// yet are real, valid data (a phase not scheduled yet), just not something a Gantt bar can
// represent. They're filtered out here rather than the server making that call for every caller
// of get_activity_gantt_rows.
function drawable_tasks() {
	return (data.value || []).filter((task) => task.start && task.end);
}

function render() {
	if (!container.value) return;
	const tasks = drawable_tasks();
	if (!tasks.length) {
		if (gantt_instance) {
			container.value.innerHTML = "";
			gantt_instance = null;
		}
		return;
	}

	if (gantt_instance) {
		gantt_instance.refresh(tasks);
		gantt_instance.change_view_mode(view_mode.value);
		return;
	}

	gantt_instance = new window.Gantt(container.value, tasks, {
		view_mode: view_mode.value,
		date_format: "YYYY-MM-DD",
		on_click: (task) => emit("open-activity", task.id),
	});
}

async function reload_and_render() {
	// `loading` flips true for the duration of `reload()`, which swaps the template to
	// LoadingState and unmounts `container`'s DOM node — any previous Gantt instance is now
	// pointing at a detached element. Drop it so `render()` builds a fresh one against whatever
	// node mounts next, instead of silently updating an element nobody can see.
	gantt_instance = null;
	await reload();
	await ensure_libs();
	// The `v-else` template branch that holds `container` only mounts once `loading` flips false
	// and there's something drawable — wait for that DOM update before touching the ref.
	await nextTick();
	render();
}

watch(() => props.project, reload_and_render, { immediate: true });
watch(view_mode, () => gantt_instance && gantt_instance.change_view_mode(view_mode.value));

onBeforeUnmount(() => {
	gantt_instance = null;
});
</script>

<template>
	<div class="hub-gantt">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload_and_render" />
		<EmptyState
			v-else-if="!drawable_tasks().length"
			:title="__('Nothing to plot yet')"
			:description="__('Gantt bars need at least a Planned Start and Planned Finish — set them from the Activity detail drawer.')"
		/>

		<template v-else>
			<div class="hub-gantt__toolbar">
				<button
					v-for="mode in VIEW_MODES"
					:key="mode"
					type="button"
					class="btn btn-xs"
					:class="mode === view_mode ? 'btn-primary' : 'btn-default'"
					@click="view_mode = mode"
				>
					{{ __(mode) }}
				</button>
				<span class="hub-gantt__hint">{{ __("Double-click a bar to open its Activity") }}</span>
			</div>
			<div ref="container" class="hub-gantt__canvas"></div>
		</template>
	</div>
</template>

<style scoped>
.hub-gantt__toolbar {
	display: flex;
	align-items: center;
	gap: 6px;
	margin-bottom: 12px;
}

.hub-gantt__hint {
	margin-left: 8px;
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.hub-gantt__canvas {
	overflow-x: auto;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
}

/* frappe-gantt renders bar/label text using its own inline styles tuned for the Desk's own
   palette — these overrides just keep it legible against the Hub's ground in both themes rather
   than pulling in the whole of Desk's Gantt CSS module. */
.hub-gantt__canvas :deep(.gantt-container) {
	background: var(--fg-color);
}

.hub-gantt__canvas :deep(.gantt .grid-background) {
	fill: var(--fg-color);
}

.hub-gantt__canvas :deep(.gantt .tick) {
	stroke: var(--border-color);
}

.hub-gantt__canvas :deep(.gantt .today-highlight) {
	fill: var(--yellow-100, #fff3cd);
}
</style>
