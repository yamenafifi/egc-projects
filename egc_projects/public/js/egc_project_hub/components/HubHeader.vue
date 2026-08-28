<!-- Tool header row — Procore's "gear icon + TOOL NAME" position, directly below the top bar.
     Project identity (name/status/progress) and navigation (project switcher, Toolbox) both live
     in HubTopBar.vue now; this row is purely "what tool am I in, what can I do with it." -->
<script setup>
import { useHubRoute } from "../composables/useHubRoute";

defineProps({
	label: { type: String, required: true },
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { setTab } = useHubRoute();

function goto_project_info() {
	setTab("project-info");
}
</script>

<template>
	<div class="egc-toolheader">
		<h2 class="egc-toolheader__title">{{ label }}</h2>

		<div class="egc-toolheader__actions">
			<button type="button" class="btn btn-sm btn-default" @click="goto_project_info">
				{{ __("Project Details") }}
			</button>
		</div>
	</div>
</template>

<style scoped>
.egc-toolheader {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	padding: 14px 24px;
	border-bottom: 1px solid var(--border-color);
	background: var(--fg-color);
	flex: 0 0 auto;
}

.egc-toolheader__title {
	font-size: var(--text-xl, 20px);
	font-weight: 600;
	color: var(--text-color);
	margin: 0;
}

.egc-toolheader__actions {
	display: flex;
	align-items: center;
	gap: 8px;
	flex: 0 0 auto;
}
</style>
