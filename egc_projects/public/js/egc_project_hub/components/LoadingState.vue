<script setup>
defineProps({
	rows: { type: Number, default: 4 },
});
</script>

<template>
	<div class="hub-loading" role="status" :aria-label="__('Loading')">
		<div v-for="n in rows" :key="n" class="hub-loading__bar" :style="{ width: 100 - n * 6 + '%' }" />
	</div>
</template>

<style scoped>
.hub-loading {
	display: flex;
	flex-direction: column;
	gap: 10px;
	padding: 4px 2px;
}

.hub-loading__bar {
	height: 14px;
	border-radius: var(--border-radius);
	background: linear-gradient(
		90deg,
		var(--control-bg) 25%,
		var(--gray-100) 37%,
		var(--control-bg) 63%
	);
	background-size: 400% 100%;
	animation: hub-shimmer 1.4s ease infinite;
}

@keyframes hub-shimmer {
	0% {
		background-position: 100% 50%;
	}
	100% {
		background-position: 0 50%;
	}
}
</style>
