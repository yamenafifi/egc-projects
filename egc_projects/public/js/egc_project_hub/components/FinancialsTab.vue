<script setup>
import { computed, watch } from "vue";
import { get_financials } from "../api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const has_access = computed(() => Boolean(props.context?.permissions?.financials));

const { data, loading, error, reload } = useHubResource(() => get_financials(props.project));

watch(
	() => [props.project, has_access.value],
	() => {
		// Never call get_financials() when the caller has no financial visibility — the tab
		// isn't even shown in that case, but this guard keeps the component safe standalone.
		if (has_access.value) reload();
	},
	{ immediate: true }
);

function format_currency(value) {
	if (value === null || value === undefined) return "—";
	return frappe.format(value, { fieldtype: "Currency", options: data.value?.currency });
}

function format_percent(value) {
	if (value === null || value === undefined) return "—";
	return `${frappe.format(value, { fieldtype: "Float", precision: 2 })}%`;
}

const rows = computed(() => {
	if (!data.value) return [];
	const d = data.value;
	return [
		{ label: __("Billed"), value: format_currency(d.billed) },
		{ label: __("Purchase Cost"), value: format_currency(d.purchase_cost) },
		{ label: __("Expense Claims"), value: format_currency(d.expense_claims) },
		{ label: __("Consumed Material Cost"), value: format_currency(d.consumed_material_cost) },
		{ label: __("Timesheet Cost"), value: format_currency(d.timesheet_cost) },
		{ label: __("Billable"), value: format_currency(d.billable) },
		{ label: __("Sales Order Value"), value: format_currency(d.sales_order_value) },
		{ label: __("Estimated Costing"), value: format_currency(d.estimated_costing) },
		{ label: __("Gross Margin"), value: format_currency(d.gross_margin), emphasis: true },
		{ label: __("% Gross Margin"), value: format_percent(d.per_gross_margin), emphasis: true },
	];
});
</script>

<template>
	<div class="hub-financials">
		<EmptyState
			v-if="!has_access"
			:title="__('Financials are not visible to you')"
			:description="__('Ask a Project Manager or Accounts role for access to project financial figures.')"
		/>
		<LoadingState v-else-if="loading" :rows="6" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />
		<EmptyState v-else-if="!data" :title="__('No financial data yet')" />

		<div v-else class="hub-financials__grid">
			<div v-for="row in rows" :key="row.label" class="hub-card hub-financials__tile" :class="{ 'hub-financials__tile--emphasis': row.emphasis }">
				<div class="hub-financials__label">{{ row.label }}</div>
				<div class="hub-financials__value">{{ row.value }}</div>
			</div>
		</div>
	</div>
</template>

<style scoped>
.hub-financials__grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
	gap: 14px;
}

.hub-financials__tile {
	padding: 16px;
}

.hub-financials__tile--emphasis {
	border-color: var(--dark-green-200, var(--green-200));
	background: var(--bg-green, var(--fg-color));
}

.hub-financials__label {
	font-size: var(--text-xs);
	color: var(--text-muted);
	margin-bottom: 6px;
}

.hub-financials__value {
	font-size: var(--text-lg);
	font-weight: 600;
	color: var(--text-color);
}
</style>
