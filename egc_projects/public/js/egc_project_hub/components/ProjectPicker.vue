<script setup>
import { ref } from "vue";
import ProjectLinkControl from "./ProjectLinkControl.vue";

const emit = defineEmits(["select"]);
const selected = ref("");

function on_change(value) {
	selected.value = value;
	if (value) emit("select", value);
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
	max-width: 420px;
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
</style>
