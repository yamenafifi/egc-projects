<script setup>
import { computed, watch } from "vue";
import { get_financials, get_financial_transactions, get_cost_forecast } from "../api";
import { get_contract_value_breakdown } from "./change_orders_api";
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

const {
	data: contract_value,
	loading: contract_value_loading,
	error: contract_value_error,
	reload: reload_contract_value,
} = useHubResource(() => get_contract_value_breakdown(props.project));

const {
	data: cost_forecast,
	loading: cost_forecast_loading,
	error: cost_forecast_error,
	reload: reload_cost_forecast,
} = useHubResource(() => get_cost_forecast(props.project));

// A client-side hint only — EGC Change Order's own DocType permissions are the actual boundary.
const WRITE_ROLES = ["EGC Project Manager", "System Manager"];
const can_write_change_orders = computed(() =>
	(frappe.user_roles || []).some((role) => WRITE_ROLES.includes(role))
);

watch(
	() => [props.project, has_access.value],
	() => {
		// Never call get_financials() when the caller has no financial visibility — the tab
		// isn't even shown in that case, but this guard keeps the component safe standalone.
		if (has_access.value) {
			reload();
			reload_contract_value();
			reload_cost_forecast();
		}
	},
	{ immediate: true }
);

function format_contract_amount(value) {
	if (value === null || value === undefined) return "—";
	return format_currency(value, data.value?.currency);
}

const change_orders_pct = computed(() => {
	if (!contract_value.value || !contract_value.value.total) return 0;
	return Math.round((contract_value.value.change_orders_total / contract_value.value.total) * 100);
});

function open_new_change_order() {
	frappe.new_doc("EGC Change Order", { project: props.project });
}

function open_change_order(name) {
	frappe.set_route("Form", "EGC Change Order", name);
}

// Spent-vs-remaining is measured against the FORECASTED total cost (estimate_at_completion), not
// the original budget — once spending is running inefficiently the forecast is the honest "100%"
// to bar against, otherwise "spent" could show past the end of its own bar.
const spent_pct = computed(() => {
	if (!cost_forecast.value || !cost_forecast.value.estimate_at_completion) return 0;
	return Math.round((cost_forecast.value.actual_cost / cost_forecast.value.estimate_at_completion) * 100);
});

const is_over_budget = computed(
	() => cost_forecast.value && cost_forecast.value.estimate_at_completion > cost_forecast.value.budget + 0.01
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

		<div class="hub-card hub-contract-value">
			<div class="hub-contract-value__head">
				<div class="hub-financials__label">{{ __("Contract Value") }}</div>
				<button
					v-if="can_write_change_orders"
					type="button"
					class="btn btn-xs btn-default"
					@click="open_new_change_order"
				>
					{{ __("New Change Order") }}
				</button>
			</div>

			<LoadingState v-if="contract_value_loading" :rows="2" />
			<ErrorState v-else-if="contract_value_error" :message="contract_value_error" @retry="reload_contract_value" />

			<template v-else-if="contract_value">
				<div class="hub-contract-value__total">{{ format_contract_amount(contract_value.total) }}</div>

				<div class="hub-contract-value__bar">
					<div class="hub-contract-value__bar-fill" :style="{ width: change_orders_pct + '%' }" />
				</div>

				<div class="hub-contract-value__breakdown">
					<div class="hub-contract-value__item">
						<span class="hub-contract-value__swatch hub-contract-value__swatch--original" />
						{{ __("Original Scope") }}
						<strong>{{ format_contract_amount(contract_value.original_scope_total) }}</strong>
					</div>
					<div class="hub-contract-value__item">
						<span class="hub-contract-value__swatch hub-contract-value__swatch--co" />
						{{ __("Change Orders") }}
						<strong>{{ format_contract_amount(contract_value.change_orders_total) }}</strong>
						<span class="hub-contract-value__pct">({{ change_orders_pct }}%)</span>
					</div>
				</div>

				<EmptyState v-if="!contract_value.change_orders.length" :title="__('No approved Change Orders yet')" />
				<ul v-else class="hub-contract-value__list">
					<li v-for="co in contract_value.change_orders" :key="co.name" @click="open_change_order(co.name)">
						<span class="hub-contract-value__co-number">{{ co.co_number }}</span>
						<span class="hub-contract-value__co-title">{{ co.title }}</span>
						<span class="hub-contract-value__co-amount">{{ format_contract_amount(co.amount) }}</span>
					</li>
				</ul>
			</template>
		</div>

		<div class="hub-card hub-cost-forecast">
			<div class="hub-cost-forecast__title-row">
				<div class="hub-financials__label">{{ __("Cost to Complete") }}</div>
				<span class="hub-cost-forecast__experimental-tag" :title="__('This estimate has no real cost-loaded budget behind it yet — treat it as a rough indicator, never a contractual figure.')">
					{{ __("Experimental") }}
				</span>
			</div>

			<LoadingState v-if="cost_forecast_loading" :rows="2" />
			<ErrorState v-else-if="cost_forecast_error" :message="cost_forecast_error" @retry="reload_cost_forecast" />

			<EmptyState
				v-else-if="cost_forecast && !cost_forecast.budget"
				:title="__('No budget set yet')"
				:description="__('Set Estimated Costing on the Project to forecast remaining cost from progress.')"
			/>

			<template v-else-if="cost_forecast">
				<p class="hub-cost-forecast__disclaimer">
					{{
						__(
							"Estimated from overall physical Activity progress against a single project budget figure — not a certified earned-value calculation from cost-loaded activities. Use as a rough indicator, not a contractual forecast."
						)
					}}
				</p>
				<div class="hub-cost-forecast__row">
					<div class="hub-cost-forecast__stat">
						<div class="hub-cost-forecast__stat-label">{{ __("Spent to Date") }}</div>
						<div class="hub-cost-forecast__stat-value">{{ format_contract_amount(cost_forecast.actual_cost) }}</div>
					</div>
					<div class="hub-cost-forecast__stat">
						<div class="hub-cost-forecast__stat-label">
							{{ __("Remaining to Spend") }}
							<span v-if="is_over_budget" class="hub-cost-forecast__over-tag">{{ __("Over Budget") }}</span>
						</div>
						<div class="hub-cost-forecast__stat-value hub-cost-forecast__stat-value--emphasis">
							{{ format_contract_amount(cost_forecast.estimate_to_complete) }}
						</div>
					</div>
				</div>

				<div class="hub-cost-forecast__bar">
					<div class="hub-cost-forecast__bar-fill" :style="{ width: Math.min(spent_pct, 100) + '%' }" />
				</div>

				<div class="hub-contract-value__breakdown">
					<div class="hub-contract-value__item">
						{{ __("Budget") }}
						<strong>{{ format_contract_amount(cost_forecast.budget) }}</strong>
					</div>
					<div class="hub-contract-value__item">
						{{ __("Physical % Complete (weighted, not cost-based)") }}
						<strong>{{ Math.round(cost_forecast.percent_complete) }}%</strong>
					</div>
					<div class="hub-contract-value__item" :class="{ 'hub-cost-forecast__over-text': is_over_budget }">
						{{ __("Forecasted Total Cost") }}
						<strong>{{ format_contract_amount(cost_forecast.estimate_at_completion) }}</strong>
					</div>
				</div>
			</template>
		</div>

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

.hub-contract-value {
	padding: 16px 18px;
	margin-bottom: 14px;
}

.hub-contract-value__head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 6px;
}

.hub-contract-value__total {
	font-size: var(--text-2xl, 28px);
	font-weight: 700;
	color: var(--text-color);
	margin-bottom: 12px;
}

.hub-contract-value__bar {
	height: 10px;
	border-radius: var(--border-radius-full);
	background: var(--dark-green-200, var(--green-200));
	overflow: hidden;
	margin-bottom: 12px;
}

.hub-contract-value__bar-fill {
	height: 100%;
	background: var(--orange-500, var(--yellow-500));
}

.hub-contract-value__breakdown {
	display: flex;
	flex-wrap: wrap;
	gap: 20px;
	margin-bottom: 14px;
}

.hub-contract-value__item {
	display: flex;
	align-items: center;
	gap: 6px;
	font-size: var(--text-sm);
	color: var(--text-muted);
}

.hub-contract-value__item strong {
	color: var(--text-color);
	font-weight: 600;
}

.hub-contract-value__pct {
	color: var(--text-muted);
	font-size: var(--text-xs);
}

.hub-contract-value__swatch {
	display: inline-block;
	width: 10px;
	height: 10px;
	border-radius: 2px;
}

.hub-contract-value__swatch--original {
	background: var(--dark-green-200, var(--green-200));
}

.hub-contract-value__swatch--co {
	background: var(--orange-500, var(--yellow-500));
}

.hub-contract-value__list {
	list-style: none;
	margin: 0;
	padding: 10px 0 0;
	border-top: 1px solid var(--border-color);
	display: flex;
	flex-direction: column;
	gap: 6px;
}

.hub-contract-value__list li {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 6px 4px;
	cursor: pointer;
	border-radius: var(--border-radius);
	font-size: var(--text-sm);
}

.hub-contract-value__list li:hover {
	background: var(--control-bg);
}

.hub-contract-value__co-number {
	font-weight: 600;
	color: var(--text-color);
	flex: 0 0 auto;
}

.hub-contract-value__co-title {
	color: var(--text-muted);
	flex: 1 1 auto;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.hub-contract-value__co-amount {
	color: var(--text-color);
	font-weight: 500;
	flex: 0 0 auto;
}

.hub-cost-forecast {
	padding: 16px 18px;
	margin-bottom: 14px;
}

.hub-cost-forecast__title-row {
	display: flex;
	align-items: center;
	gap: 8px;
}

.hub-cost-forecast__experimental-tag {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--yellow-700, var(--orange-600));
	background: var(--yellow-100, var(--bg-yellow));
	border-radius: var(--border-radius-full);
	padding: 1px 8px;
	cursor: help;
}

.hub-cost-forecast__disclaimer {
	margin: 4px 0 12px;
	font-size: var(--text-xs);
	color: var(--text-muted);
	max-width: 60ch;
}

.hub-cost-forecast__row {
	display: flex;
	gap: 32px;
	margin: 10px 0 14px;
}

.hub-cost-forecast__stat-label {
	font-size: var(--text-xs);
	color: var(--text-muted);
	margin-bottom: 4px;
	display: flex;
	align-items: center;
	gap: 8px;
}

.hub-cost-forecast__stat-value {
	font-size: var(--text-xl, 22px);
	font-weight: 700;
	color: var(--text-color);
}

.hub-cost-forecast__stat-value--emphasis {
	color: var(--dark-green-600, var(--green-600));
}

.hub-cost-forecast__over-tag {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--red-600, var(--text-on-red));
	background: var(--red-100, var(--bg-red));
	border-radius: var(--border-radius-full);
	padding: 1px 8px;
}

.hub-cost-forecast__over-text strong {
	color: var(--red-600, var(--text-on-red)) !important;
}

.hub-cost-forecast__bar {
	height: 10px;
	border-radius: var(--border-radius-full);
	background: var(--dark-green-200, var(--green-200));
	overflow: hidden;
	margin-bottom: 12px;
}

.hub-cost-forecast__bar-fill {
	height: 100%;
	background: var(--dark-green-500, var(--green-500));
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
