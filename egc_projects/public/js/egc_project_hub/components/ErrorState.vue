<script setup>
defineProps({
	message: { type: String, required: true },
});

defineEmits(["retry"]);
</script>

<template>
	<div class="hub-error">
		<div class="hub-error__icon">
			<svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
				<path
					d="M10 2 1 17h18L10 2Zm0 5.5v4.5m0 3h.01"
					stroke="currentColor"
					stroke-width="1.5"
					stroke-linecap="round"
					stroke-linejoin="round"
				/>
			</svg>
		</div>
		<div class="hub-error__message">{{ message }}</div>
		<button class="btn btn-sm btn-default" @click="$emit('retry')">{{ __("Retry") }}</button>
	</div>
</template>

<style scoped>
.hub-error {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	text-align: center;
	padding: 40px 24px;
	gap: 10px;
}

.hub-error__icon {
	color: var(--red-500, var(--text-on-red));
	background: var(--bg-red);
	border-radius: 50%;
	width: 40px;
	height: 40px;
	display: flex;
	align-items: center;
	justify-content: center;
}

.hub-error__message {
	color: var(--text-color);
	font-size: var(--text-sm);
	max-width: 420px;
}
</style>
