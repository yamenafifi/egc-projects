<script setup>
import { computed, watch } from "vue";
import { get_financials, get_financial_transactions } from "../api";
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

function format_amount(value) {
	if (value === null || value === undefined) return "—";
	// format_currency() returns a plain string ("AED 140,400.00"); frappe.format() wraps
	// Currency values in a <div style="text-align:right">…</div> meant for v-html contexts,
	// which would render as literal markup in a plain text interpolation here.
	return format_currency(value, data.value?.currency);
}

function format_percent(value) {
	if (value === null || value === undefined) return "—";
	return `${flt(value, 2)}%`;
}

// A Currency record whose `symbol` is blank (SAR is a single space in some ERPNext datasets)
// formats to a bare number. On a financials screen an amount with no currency indicator is
// genuinely ambiguous, so state the currency once above the grid rather than trusting the
// symbol to carry it.
const currency_note = computed(() =>
	data.value?.currency ? __("All amounts in {0}", [data.value.currency]) : ""
);

// Only these six figures are backed by a single, well-defined set of underlying ERPNext
// transactions (docs/ARCHITECTURE_V2.md §10) — `billable`/`estimated_costing`/`gross_margin`/
// `per_gross_margin` are derived/computed values with no one-to-one transaction list behind
// them, so they stay plain tiles rather than getting a drill-down that couldn't reconcile.
const rows = computed(() => {
	if (!data.value) return [];
	const d = data.value;
	return [
		{ label: __("Billed"), value: format_amount(d.billed), metric: "billed" },
		{ label: __("Purchase Cost"), value: format_amount(d.purchase_cost), metric: "purchase_cost" },
		{ label: __("Expense Claims"), value: format_amount(d.expense_claims), metric: "expense_claims" },
		{
			label: __("Consumed Material Cost"),
			value: format_amount(d.consumed_material_cost),
			metric: "consumed_material_cost",
		},
		{ label: __("Timesheet Cost"), value: format_amount(d.timesheet_cost), metric: "timesheet_cost" },
		{ label: __("Billable"), value: format_amount(d.billable) },
		{
			label: __("Sales Order Value"),
			value: format_amount(d.sales_order_value),
			metric: "sales_order_value",
		},
		{ label: __("Estimated Costing"), value: format_amount(d.estimated_costing) },
		{ label: __("Gross Margin"), value: format_amount(d.gross_margin), emphasis: true },
		{ label: __("% Gross Margin"), value: format_percent(d.per_gross_margin), emphasis: true },
	];
});

function escape(value) {
	return frappe.utils.escape_html(value == null ? "" : String(value));
}

async function open_drill_down(row) {
	if (!row.metric) return;
	const dialog = new frappe.ui.Dialog({
		title: __("{0} — Transactions", [row.label]),
		size: "large",
		fields: [{ fieldtype: "HTML", fieldname: "transactions" }],
	});
	dialog.show();
	dialog.set_value("transactions", `<div class="text-muted">${__("Loading…")}</div>`);

	try {
		const transactions = await get_financial_transactions(props.project, row.metric);
		if (!transactions.length) {
			dialog.set_value("transactions", `<div class="text-muted">${__("No transactions found.")}</div>`);
			return;
		}
		const body = transactions
			.map(
				(t) => `<tr>
					<td>${escape(t.doctype)}</td>
					<td><a href="/app/${encodeURIComponent(frappe.router.slug(t.doctype))}/${encodeURIComponent(t.name)}" target="_blank" rel="noopener">${escape(t.name)}</a></td>
					<td>${t.date ? escape(frappe.datetime.str_to_user(t.date)) : "—"}</td>
					<td>${escape(t.reference || "—")}</td>
					<td style="text-align:right">${format_amount(t.amount)}</td>
				</tr>`
			)
			.join("");
		dialog.set_value(
			"transactions",
			`<table class="hub-table"><thead><tr>
				<th>${__("Type")}</th><th>${__("Document")}</th><th>${__("Date")}</th>
				<th>${__("Reference")}</th><th style="text-align:right">${__("Amount")}</th>
			</tr></thead><tbody>${body}</tbody></table>`
		);
	} catch (e) {
		dialog.set_value("transactions", `<div class="text-muted">${escape(e.message)}</div>`);
	}
}
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

		<template v-else>
		<div v-if="currency_note" class="hub-financials__currency">{{ currency_note }}</div>
		<div class="hub-financials__grid">
			<div
				v-for="row in rows"
				:key="row.label"
				class="hub-card hub-financials__tile"
				:class="{ 'hub-financials__tile--emphasis': row.emphasis, 'hub-financials__tile--clickable': row.metric }"
				@click="open_drill_down(row)"
			>
				<div class="hub-financials__label">{{ row.label }}</div>
				<div class="hub-financials__value">{{ row.value }}</div>
			</div>
		</div>
		</template>
	</div>
</template>

<style scoped>
.hub-financials__currency {
	font-size: var(--text-xs);
	color: var(--text-muted);
	margin-bottom: 10px;
}

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

.hub-financials__tile--clickable {
	cursor: pointer;
}

.hub-financials__tile--clickable:hover {
	border-color: var(--text-muted);
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
