<script setup>
defineProps({
	tabs: { type: Array, required: true },
	active: { type: String, required: true },
});
defineEmits(["select"]);
</script>

<template>
	<div class="hub-tabs" role="tablist">
		<button
			v-for="tab in tabs"
			:key="tab.key"
			class="hub-tabs__item"
			role="tab"
			:aria-selected="tab.key === active"
			:class="{ 'hub-tabs__item--active': tab.key === active }"
			@click="$emit('select', tab.key)"
		>
			{{ tab.label }}
		</button>
	</div>
</template>

<style scoped>
.hub-tabs {
	display: flex;
	gap: 4px;
	border-bottom: 1px solid var(--border-color);
	margin-bottom: 16px;
	overflow-x: auto;
}

.hub-tabs__item {
	appearance: none;
	background: none;
	border: none;
	padding: 9px 14px;
	font-size: var(--text-sm);
	font-weight: 500;
	color: var(--text-muted);
	border-bottom: 2px solid transparent;
	cursor: pointer;
	white-space: nowrap;
}

.hub-tabs__item:hover {
	color: var(--text-color);
}

.hub-tabs__item--active {
	color: var(--text-color);
	border-bottom-color: var(--primary, var(--blue-500));
}
</style>
