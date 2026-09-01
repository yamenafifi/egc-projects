<!-- Tool header row — Procore's "gear icon + TOOL NAME" position, directly below the top bar.
     Navigation (project switcher, Toolbox) lives in HubTopBar.vue; this row carries "what tool am
     I in" plus the project's own status/progress (moved down from HubTopBar.vue — the standalone
     "Project Details" button that used to sit here was dropped since Project Details is already
     one of the Toolbox tabs). -->
<script setup>
import StatusPill from "./StatusPill.vue";

defineProps({
	label: { type: String, required: true },
	project: { type: String, required: true },
	context: { type: Object, default: null },
});
</script>

<template>
	<div class="egc-toolheader">
		<h2 class="egc-toolheader__title">{{ label }}</h2>

		<div v-if="context" class="egc-toolheader__status">
			<StatusPill :status="context.status" />
			<div
				v-if="context.percent_complete !== null && context.percent_complete !== undefined"
				class="egc-toolheader__complete"
			>
				<div class="egc-toolheader__progress">
					<div class="egc-toolheader__progress-bar" :style="{ width: (context.percent_complete || 0) + '%' }" />
				</div>
				<span class="egc-toolheader__complete-value">{{ Math.round(context.percent_complete || 0) }}%</span>
			</div>
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

.egc-toolheader__status {
	display: flex;
	align-items: center;
	gap: 12px;
	flex: 0 0 auto;
}

.egc-toolheader__complete {
	display: flex;
	align-items: center;
	gap: 6px;
	width: 120px;
}

.egc-toolheader__progress {
	flex: 1;
	height: 6px;
	border-radius: var(--border-radius-full);
	background: var(--control-bg);
	overflow: hidden;
}

.egc-toolheader__progress-bar {
	height: 100%;
	background: var(--dark-green-500, var(--green-500));
	border-radius: var(--border-radius-full);
}

.egc-toolheader__complete-value {
	font-size: var(--text-xs);
	color: var(--text-muted);
	width: 30px;
	text-align: right;
}
</style>
