<script setup>
import { ref, onMounted } from "vue";
import ProjectLinkControl from "./ProjectLinkControl.vue";
import { get_my_projects } from "../api";

const emit = defineEmits(["select"]);
const selected = ref("");

const loading = ref(true);
const error = ref("");
const projects = ref([]);

onMounted(async () => {
	try {
		projects.value = await get_my_projects();
	} catch (e) {
		error.value = e.message;
	} finally {
		loading.value = false;
	}
});

function on_change(value) {
	selected.value = value;
	// Selecting a project here causes the parent to swap this whole picker out for the header
	// + tabs (see EgcProjectHub.vue's v-if="!route.project"), unmounting ProjectLinkControl's
	// DOM. Frappe's own Link control keeps running async validation after invoking our change
	// handler, so emit on the next macrotask to let that finish first — see the identical fix
	// in HubHeader.vue's on_switch for the full explanation.
	if (value) setTimeout(() => emit("select", value), 0);
}

function open(project) {
	emit("select", project.name);
}
</script>

<template>
	<div class="hub-picker">
		<div class="hub-picker__card">
			<div class="hub-picker__title">{{ __("Open a project") }}</div>
			<div class="hub-picker__description">
				{{ __("Pick a project to see its WBS, activities, submittals, drawings and financials in one place.") }}
			</div>
			<ProjectLinkControl
				:model-value="selected"
				:placeholder="__('Search projects…')"
				@update:model-value="on_change"
			/>

			<div class="hub-picker__list">
				<div v-if="loading" class="hub-picker__status">{{ __("Loading your projects…") }}</div>
				<div v-else-if="error" class="hub-picker__status hub-picker__status--error">{{ error }}</div>
				<div v-else-if="!projects.length" class="hub-picker__status">
					{{ __("You don't have access to any projects yet. Ask your Project Manager to add you to a project's Directory and grant you access.") }}
				</div>
				<ul v-else class="hub-picker__projects">
					<li v-for="project in projects" :key="project.name">
						<button type="button" class="hub-picker__project" @click="open(project)">
							<span class="hub-picker__project-name">{{ project.project_name || project.name }}</span>
							<span class="hub-picker__project-code">{{ project.name }}</span>
							<span class="hub-picker__project-status">{{ project.status }}</span>
						</button>
					</li>
				</ul>
			</div>
		</div>
	</div>
</template>

<style scoped>
.hub-picker {
	display: flex;
	align-items: center;
	justify-content: center;
	min-height: 50vh;
	padding: 24px;
}

.hub-picker__card {
	width: 100%;
	max-width: 480px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	background: var(--fg-color);
	padding: 28px;
	text-align: center;
}

.hub-picker__title {
	font-size: var(--text-lg);
	font-weight: 600;
	color: var(--text-color);
	margin-bottom: 6px;
}

.hub-picker__description {
	font-size: var(--text-sm);
	color: var(--text-muted);
	margin-bottom: 18px;
}

.hub-picker :deep(.hub-project-link) {
	text-align: left;
}

.hub-picker__list {
	margin-top: 20px;
	text-align: left;
}

.hub-picker__status {
	font-size: var(--text-sm);
	color: var(--text-muted);
	text-align: center;
	padding: 12px 4px;
}

.hub-picker__status--error {
	color: var(--red-500, var(--text-on-red));
}

.hub-picker__projects {
	list-style: none;
	margin: 0;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 6px;
	max-height: 320px;
	overflow-y: auto;
}

.hub-picker__project {
	appearance: none;
	width: 100%;
	display: flex;
	align-items: center;
	gap: 10px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	padding: 8px 12px;
	cursor: pointer;
	text-align: left;
}

.hub-picker__project:hover {
	background: var(--control-bg);
}

.hub-picker__project-name {
	flex: 1 1 auto;
	font-size: var(--text-sm);
	color: var(--text-color);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.hub-picker__project-code {
	flex: 0 0 auto;
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.hub-picker__project-status {
	flex: 0 0 auto;
	font-size: var(--text-xs);
	color: var(--text-muted);
	background: var(--control-bg);
	border-radius: var(--border-radius);
	padding: 2px 8px;
}
</style>
