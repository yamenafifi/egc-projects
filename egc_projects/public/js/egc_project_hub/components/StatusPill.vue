<script setup>
import { computed } from "vue";
import { statusColor, OVERDUE_COLOR } from "../composables/useStatusColor";

const props = defineProps({
	status: { type: String, default: "" },
	overdue: { type: Boolean, default: false },
});

const color = computed(() => (props.overdue ? OVERDUE_COLOR : statusColor(props.status)));
</script>

<template>
	<span class="indicator-pill" :class="color">{{ overdue ? __("Overdue") : status || __("—") }}</span>
</template>
