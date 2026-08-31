<!-- A clean, at-a-glance review-chain visualization — the Hub's version of Aconex's "Workflow
     Steps" panel (research: help.aconex.com's Doc Mode screen shows a right-side panel of
     completed/current/pending workflow steps as a connected chain). Purely presentational and
     read-only: SubmittalDetail.vue's own "Reviewers" card keeps the interactive Respond/Remove
     controls, this renders ABOVE that as a compact summary of the same `stages` data; a
     Document's own page uses it identically (read-only) to show its governing Submittal's
     progress without leaving the Document. One component, two consumers, never a third divergent
     rendering of "what does this review chain look like." -->
<script setup>
const props = defineProps({
	// [{ sequence, steps: [{ name, reviewer_role, reviewer_label, status, response }] }]
	stages: { type: Array, required: true },
	compact: { type: Boolean, default: false },
});

const RESPONSE_OK = ["Approved", "Approved with Comments"];

function stepTone(step) {
	if (step.status === "Responded") {
		if (RESPONSE_OK.includes(step.response)) return "green";
		if (step.response === "Rejected") return "red";
		if (step.response === "Revise & Resubmit") return "orange";
	}
	if (step.status === "In Review") return "blue";
	return "grey";
}

function stepIcon(step) {
	if (step.status === "Responded") {
		if (RESPONSE_OK.includes(step.response)) return "✓";
		if (step.response === "Rejected") return "✕";
		if (step.response === "Revise & Resubmit") return "↺";
	}
	if (step.status === "In Review") return "●";
	if (step.status === "Skipped") return "—";
	return "○";
}

function stepLabel(step) {
	return step.reviewer_label || step.reviewer_role || __("Reviewer");
}

// A stage "as a whole" tone, for the connecting rail dot — green only once every required step
// in it has a final OK response; red/orange if any step in it ended the cycle; blue if anything
// in it is still being looked at; grey otherwise (Pending).
function stageTone(stage) {
	const steps = stage.steps || [];
	if (steps.some((s) => s.status === "Responded" && !RESPONSE_OK.includes(s.response))) {
		return steps.find((s) => s.response === "Rejected") ? "red" : "orange";
	}
	if (steps.length && steps.every((s) => s.status === "Responded" || s.status === "Skipped")) return "green";
	if (steps.some((s) => s.status === "In Review")) return "blue";
	return "grey";
}
</script>

<template>
	<div class="workflow-stepper" :class="{ 'workflow-stepper--compact': compact }">
		<div v-for="(stage, idx) in stages" :key="stage.sequence" class="workflow-stepper__stage">
			<div class="workflow-stepper__rail">
				<span class="workflow-stepper__stage-dot" :class="`workflow-stepper__stage-dot--${stageTone(stage)}`">
					{{ stage.sequence }}
				</span>
				<span v-if="idx < stages.length - 1" class="workflow-stepper__rail-line" />
			</div>
			<div class="workflow-stepper__steps">
				<div v-for="step in stage.steps" :key="step.name || stepLabel(step)" class="workflow-stepper__step">
					<span class="workflow-stepper__dot" :class="`workflow-stepper__dot--${stepTone(step)}`">
						{{ stepIcon(step) }}
					</span>
					<span class="workflow-stepper__label">{{ stepLabel(step) }}</span>
					<span class="workflow-stepper__state">{{ step.status === "Responded" ? step.response : step.status }}</span>
				</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.workflow-stepper {
	display: flex;
	flex-direction: column;
}

.workflow-stepper__stage {
	display: flex;
	gap: 10px;
}

.workflow-stepper__rail {
	display: flex;
	flex-direction: column;
	align-items: center;
	flex: 0 0 auto;
}

.workflow-stepper__stage-dot {
	width: 20px;
	height: 20px;
	flex: 0 0 auto;
	border-radius: 50%;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 11px;
	font-weight: 700;
	background: var(--control-bg);
	color: var(--text-muted);
	border: 1px solid var(--border-color);
}

.workflow-stepper__stage-dot--green {
	color: var(--green-500, #2e7d32);
	border-color: var(--green-200, var(--green-500, #2e7d32));
}

.workflow-stepper__stage-dot--red {
	color: var(--red-500, #d1483e);
	border-color: var(--red-200, var(--red-500, #d1483e));
}

.workflow-stepper__stage-dot--orange {
	color: var(--orange-500, #d98c26);
	border-color: var(--orange-200, var(--orange-500, #d98c26));
}

.workflow-stepper__stage-dot--blue {
	color: var(--blue-500, #2f6fed);
	border-color: var(--blue-200, var(--blue-500, #2f6fed));
}

.workflow-stepper__rail-line {
	flex: 1 1 auto;
	width: 1px;
	background: var(--border-color);
	min-height: 10px;
}

.workflow-stepper__stage:last-child .workflow-stepper__rail-line {
	display: none;
}

.workflow-stepper__steps {
	flex: 1 1 auto;
	min-width: 0;
	display: flex;
	flex-direction: column;
	gap: 6px;
	padding-bottom: 14px;
}

.workflow-stepper__step {
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: var(--text-sm);
}

.workflow-stepper__dot {
	width: 16px;
	height: 16px;
	flex: 0 0 auto;
	border-radius: 50%;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 9px;
	font-weight: 700;
	background: var(--control-bg);
	color: var(--text-muted);
	border: 1px solid var(--border-color);
}

.workflow-stepper__dot--green {
	color: var(--green-500, #2e7d32);
	border-color: var(--green-200, var(--green-500, #2e7d32));
}

.workflow-stepper__dot--red {
	color: var(--red-500, #d1483e);
	border-color: var(--red-200, var(--red-500, #d1483e));
}

.workflow-stepper__dot--orange {
	color: var(--orange-500, #d98c26);
	border-color: var(--orange-200, var(--orange-500, #d98c26));
}

.workflow-stepper__dot--blue {
	color: var(--blue-500, #2f6fed);
	border-color: var(--blue-200, var(--blue-500, #2f6fed));
}

.workflow-stepper__label {
	color: var(--text-color);
	white-space: nowrap;
	overflow: hidden;
	text-overflow: ellipsis;
}

.workflow-stepper__state {
	margin-left: auto;
	font-size: var(--text-xs);
	color: var(--text-muted);
	white-space: nowrap;
}

.workflow-stepper--compact .workflow-stepper__steps {
	gap: 4px;
	padding-bottom: 10px;
}

.workflow-stepper--compact .workflow-stepper__step {
	font-size: var(--text-xs);
}
</style>
