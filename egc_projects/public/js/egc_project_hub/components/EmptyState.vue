<script setup>
defineProps({
	title: { type: String, required: true },
	description: { type: String, default: "" },
	actionLabel: { type: String, default: "" },
});

defineEmits(["action"]);
</script>

<template>
	<div class="hub-empty">
		<div class="hub-empty__title">{{ title }}</div>
		<div v-if="description" class="hub-empty__description">{{ description }}</div>
		<button v-if="actionLabel" class="btn btn-sm btn-default hub-empty__action" @click="$emit('action')">
			{{ actionLabel }}
		</button>
	</div>
</template>

<style scoped>
.hub-empty {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	text-align: center;
	padding: 48px 24px;
	color: var(--text-muted);
}

.hub-empty__title {
	font-size: var(--text-md);
	font-weight: 500;
	color: var(--text-color);
	margin-bottom: 4px;
}

.hub-empty__description {
	font-size: var(--text-sm);
	max-width: 360px;
}

.hub-empty__action {
	margin-top: 14px;
}
</style>
