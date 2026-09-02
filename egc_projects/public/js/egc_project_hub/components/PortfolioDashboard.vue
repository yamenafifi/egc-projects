<!-- The bare `/app/project-manager` landing dashboard, shown only to a financial-access user
     (EgcProjectHub.vue's own gate) — everyone else still gets ProjectPicker, unchanged. Replaces
     the old silent "jump to whatever project was last open" localStorage redirect with an actual
     page: portfolio-wide financial totals, which projects need attention, and a sortable
     per-project breakdown so "which project needs paying" or "which is bringing money in" is a
     one-click sort, not a mental tally across N separately-opened Financials tabs.

     No HubTopBar/HubHeader chrome, same as ProjectPicker — there's no single project to drive
     a project-switcher header with. Clicking a project row emits "select", exactly like
     ProjectPicker's own contract, so EgcProjectHub.vue needs no special-casing beyond the
     existing @select="setProject" it already wires up. -->
<script setup>
import { ref, computed, onMounted } from "vue";
import { get_portfolio_overview } from "../api";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";

const emit = defineEmits(["select"]);

const loading = ref(true);
const error = ref("");
const data = ref(null);

async function load() {
	loading.value = true;
	error.value = "";
	try {
		data.value = await get_portfolio_overview();
	} catch (e) {
		error.value = e.message;
	} finally {
		loading.value = false;
	}
}
onMounted(load);

function open(project) {
	emit("select", project);
}

// -- currency-grouped summary tiles ------------------------------------------------------------
// Never blindly summed across currencies — a portfolio spanning more than one Company would
// otherwise silently add e.g. SAR and USD together into a meaningless total. One tile-group per
// currency actually present; the common case (a single Company) renders as just one group with
// no currency label needed.

const TILE_METRICS = [
	{ key: "billed", label: __("Billed") },
	{ key: "committed_purchase_orders", label: __("Committed POs — money still to pay") },
	{ key: "sales_order_value", label: __("Sales Order Value") },
	{ key: "consumed_material_cost", label: __("Consumed Material") },
	{ key: "timesheet_cost", label: __("Timesheet Cost") },
	{ key: "gross_margin", label: __("Gross Margin"), emphasis: true },
];

const currency_groups = computed(() => {
	const projects = data.value?.projects || [];
	const groups = new Map();
	for (const row of projects) {
		const currency = row.financials?.currency || __("Unspecified");
		if (!groups.has(currency)) {
			groups.set(currency, { currency, count: 0, totals: {} });
		}
		const group = groups.get(currency);
		group.count += 1;
		for (const metric of TILE_METRICS) {
			group.totals[metric.key] = (group.totals[metric.key] || 0) + (row.financials?.[metric.key] || 0);
		}
	}
	return [...groups.values()];
});

function format_money(value, currency) {
	return frappe.format(value || 0, { fieldtype: "Currency", options: currency || undefined });
}

// -- health rollup --------------------------------------------------------------------------

const health_counts = computed(() => {
	const projects = data.value?.projects || [];
	let red = 0;
	let orange = 0;
	for (const row of projects) {
		const signals = Object.values(row.health || {});
		if (signals.includes("red")) red += 1;
		else if (signals.includes("orange")) orange += 1;
	}
	return { red, orange, green: projects.length - red - orange, total: projects.length };
});

// -- sortable per-project table ---------------------------------------------------------------

const sort_key = ref("committed_purchase_orders");
const sort_desc = ref(true);

const COLUMNS = [
	{ key: "project_name", label: __("Project") },
	{ key: "status", label: __("Status") },
	{ key: "billed", label: __("Billed") },
	{ key: "committed_purchase_orders", label: __("Committed POs") },
	{ key: "sales_order_value", label: __("Sales Order Value") },
	{ key: "gross_margin", label: __("Gross Margin") },
];

function set_sort(key) {
	if (sort_key.value === key) {
		sort_desc.value = !sort_desc.value;
	} else {
		sort_key.value = key;
		sort_desc.value = true;
	}
}

function sort_value(row, key) {
	if (key === "project_name") return (row.project_name || row.project || "").toLowerCase();
	if (key === "status") return (row.status || "").toLowerCase();
	return row.financials?.[key] ?? 0;
}

const sorted_projects = computed(() => {
	const rows = [...(data.value?.projects || [])];
	rows.sort((a, b) => {
		const av = sort_value(a, sort_key.value);
		const bv = sort_value(b, sort_key.value);
		if (av < bv) return sort_desc.value ? 1 : -1;
		if (av > bv) return sort_desc.value ? -1 : 1;
		return 0;
	});
	return rows;
});

function health_dot(row) {
	const signals = Object.values(row.health || {});
	if (signals.includes("red")) return "red";
	if (signals.includes("orange")) return "orange";
	return "green";
}
</script>

<template>
	<div class="portfolio-dashboard">
		<div class="portfolio-dashboard__header">
			<h1 class="portfolio-dashboard__title">{{ __("Portfolio Overview") }}</h1>
			<p class="portfolio-dashboard__subtitle">
				{{ __("Every project you can see, rolled up — pick one below to open it.") }}
			</p>
		</div>

		<LoadingState v-if="loading" :rows="6" />
		<ErrorState v-else-if="error" :message="error" @retry="load" />
		<EmptyState
			v-else-if="!(data?.projects || []).length"
			:title="__('No projects yet')"
			:description="__('Nothing to show here until at least one project exists.')"
		/>

		<template v-else>
			<div v-for="group in currency_groups" :key="group.currency" class="portfolio-dashboard__tiles">
				<div class="portfolio-dashboard__tiles-label" v-if="currency_groups.length > 1">
					{{ __("{0} — {1} project(s)", [group.currency, group.count]) }}
				</div>
				<div class="portfolio-tiles">
					<div
						v-for="metric in TILE_METRICS"
						:key="metric.key"
						class="portfolio-tile hub-card"
						:class="{ 'portfolio-tile--emphasis': metric.emphasis }"
					>
						<div class="portfolio-tile__label">{{ metric.label }}</div>
						<div class="portfolio-tile__value">{{ format_money(group.totals[metric.key], group.currency) }}</div>
					</div>
				</div>
			</div>

			<div class="portfolio-dashboard__row">
				<div class="hub-card portfolio-dashboard__health">
					<div class="hub-card__title">{{ __("Project Health") }}</div>
					<div class="portfolio-health__strip">
						<span class="portfolio-health__item portfolio-health__item--green">{{ __("{0} on track", [health_counts.green]) }}</span>
						<span class="portfolio-health__item portfolio-health__item--orange">{{ __("{0} watch", [health_counts.orange]) }}</span>
						<span class="portfolio-health__item portfolio-health__item--red">{{ __("{0} need attention", [health_counts.red]) }}</span>
					</div>
				</div>

				<div class="hub-card portfolio-dashboard__attention">
					<div class="hub-card__title">{{ __("Needs Attention") }}</div>
					<ul v-if="(data.needs_attention || []).length" class="portfolio-attention__list">
						<li v-for="row in data.needs_attention" :key="row.project">
							<a href="#" class="hub-link" @click.prevent="open(row.project)">
								{{ row.project_name || row.project }}
							</a>
						</li>
					</ul>
					<p v-else class="text-muted">{{ __("Nothing needs attention right now.") }}</p>
				</div>
			</div>

			<div class="hub-table-wrap portfolio-dashboard__table">
				<table class="hub-table">
					<thead>
						<tr>
							<th v-for="col in COLUMNS" :key="col.key" class="portfolio-table__sortable" @click="set_sort(col.key)">
								{{ col.label }}
								<span v-if="sort_key === col.key">{{ sort_desc ? "↓" : "↑" }}</span>
							</th>
							<th>{{ __("Health") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in sorted_projects"
							:key="row.project"
							class="hub-table__row--clickable"
							@click="open(row.project)"
						>
							<td>{{ row.project_name || row.project }}</td>
							<td>{{ row.status }}</td>
							<td>{{ format_money(row.financials.billed, row.financials.currency) }}</td>
							<td>{{ format_money(row.financials.committed_purchase_orders, row.financials.currency) }}</td>
							<td>{{ format_money(row.financials.sales_order_value, row.financials.currency) }}</td>
							<td>{{ format_money(row.financials.gross_margin, row.financials.currency) }}</td>
							<td>
								<span class="portfolio-health__dot" :class="`portfolio-health__dot--${health_dot(row)}`"></span>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</template>
	</div>
</template>

<style scoped>
.portfolio-dashboard {
	max-width: 1200px;
	margin: 0 auto;
	padding: 24px;
	display: flex;
	flex-direction: column;
	gap: 20px;
}

.portfolio-dashboard__title {
	font-size: var(--text-2xl, 22px);
	font-weight: 600;
	color: var(--text-color);
	margin: 0 0 4px;
}

.portfolio-dashboard__subtitle {
	font-size: var(--text-sm);
	color: var(--text-muted);
	margin: 0;
}

.portfolio-dashboard__tiles-label {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-muted);
	margin-bottom: 8px;
}

.portfolio-tiles {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
	gap: 12px;
}

.portfolio-tile__label {
	font-size: var(--text-xs);
	color: var(--text-muted);
	margin-bottom: 4px;
}

.portfolio-tile__value {
	font-size: var(--text-lg);
	font-weight: 600;
	color: var(--text-color);
	font-variant-numeric: tabular-nums;
}

.portfolio-tile--emphasis .portfolio-tile__value {
	color: var(--egc-accent);
}

.portfolio-dashboard__row {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 16px;
}

.portfolio-health__strip {
	display: flex;
	gap: 16px;
	flex-wrap: wrap;
}

.portfolio-health__item {
	font-size: var(--text-sm);
	font-weight: 500;
	padding: 4px 10px;
	border-radius: var(--border-radius);
}

.portfolio-health__item--green {
	color: var(--green-600, #2e844a);
	background: var(--green-100, rgba(46, 132, 74, 0.1));
}

.portfolio-health__item--orange {
	color: var(--orange-600, #b8631e);
	background: var(--orange-100, rgba(184, 99, 30, 0.1));
}

.portfolio-health__item--red {
	color: var(--red-600, #c53434);
	background: var(--red-100, rgba(197, 52, 52, 0.1));
}

.portfolio-attention__list {
	list-style: none;
	margin: 0;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 6px;
}

.portfolio-table__sortable {
	cursor: pointer;
	user-select: none;
}

.portfolio-health__dot {
	display: inline-block;
	width: 9px;
	height: 9px;
	border-radius: 50%;
}

.portfolio-health__dot--green {
	background: var(--green-500, #2e844a);
}

.portfolio-health__dot--orange {
	background: var(--orange-500, #e67e22);
}

.portfolio-health__dot--red {
	background: var(--red-500, #c53434);
}

@media (max-width: 720px) {
	.portfolio-dashboard__row {
		grid-template-columns: 1fr;
	}
}
</style>
