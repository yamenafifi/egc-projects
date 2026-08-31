<script setup>
import { ref, computed, watch } from "vue";
import { useHubRoute, TABS } from "./composables/useHubRoute";
import { get_project_context } from "./api";
import HubHeader from "./components/HubHeader.vue";
import HubTopBar from "./components/HubTopBar.vue";
import ProjectPicker from "./components/ProjectPicker.vue";
import LoadingState from "./components/LoadingState.vue";
import ErrorState from "./components/ErrorState.vue";
import OverviewTab from "./components/OverviewTab.vue";
import WbsTab from "./components/WbsTab.vue";
import ActivitiesTab from "./components/ActivitiesTab.vue";
import SubmittalsTab from "./components/SubmittalsTab.vue";
import FinancialsTab from "./components/FinancialsTab.vue";
// WP-10/WP-09 landed while this shell was in progress — wired straight in, no placeholder left.
import DocumentsTab from "./components/DocumentsTab.vue";
import ProjectInfoTab from "./components/ProjectInfoTab.vue";
import DirectoryTab from "./components/DirectoryTab.vue";

defineProps({ page: { type: Object, default: null } });

const { route, setProject, setTab } = useHubRoute();

const TAB_LABELS = {
	overview: __("Overview"),
	wbs: __("WBS"),
	activities: __("Activities"),
	submittals: __("Submittals"),
	documents: __("Documents"),
	directory: __("Directory"),
	financials: __("Financials"),
	"project-info": __("Project Details"),
};

const context = ref(null);
const context_loading = ref(false);
const context_error = ref("");

// The Financials tab is hidden entirely (not just its content) when the user lacks financial
// visibility — the tab list only shows it once get_project_context() confirms
// permissions.financials, and get_financials() itself is never called otherwise.
const tab_defs = computed(() =>
	TABS.filter((key) => key !== "financials" || context.value?.permissions?.financials).map((key) => ({
		key,
		label: TAB_LABELS[key],
	}))
);

const tab_component = computed(() => {
	return {
		overview: OverviewTab,
		wbs: WbsTab,
		activities: ActivitiesTab,
		submittals: SubmittalsTab,
		documents: DocumentsTab,
		directory: DirectoryTab,
		financials: FinancialsTab,
		"project-info": ProjectInfoTab,
	}[route.tab];
});

async function load_context() {
	if (!route.project) return;
	context.value = null;
	context_error.value = "";
	context_loading.value = true;
	try {
		context.value = await get_project_context(route.project);
	} catch (e) {
		context_error.value = e.message;
	} finally {
		context_loading.value = false;
	}
}

watch(
	() => route.project,
	(project, previous) => {
		if (project && project !== previous) load_context();
	},
	{ immediate: true }
);

// A direct/linked URL could land on ?/financials before permissions are known, or for a user
// who never had access — bounce to Overview rather than call get_financials() speculatively.
watch(context, (ctx) => {
	if (ctx && route.tab === "financials" && !ctx.permissions?.financials) {
		setTab("overview");
	}
});
</script>

<template>
	<div class="egc-shell">
		<ProjectPicker v-if="!route.project" @select="setProject" />

		<template v-else>
			<HubTopBar
				:project="route.project"
				:project-name="context ? context.project_name : ''"
				:tabs="tab_defs"
				:active="route.tab"
				:context="context"
				@select="setTab"
				@switch-project="setProject"
			/>

			<HubHeader
				:label="TAB_LABELS[route.tab]"
				:project="route.project"
				:context="context"
			/>

			<div class="egc-shell__content">
				<ErrorState v-if="context_error" :message="context_error" @retry="load_context" />

				<template v-else>
					<LoadingState v-if="context_loading && !context" :rows="6" />

					<component
						:is="tab_component"
						v-else-if="context"
						:key="route.tab + ':' + route.project"
						:project="route.project"
						:context="context"
					/>
				</template>
			</div>
		</template>
	</div>
</template>

<style>
/* Design tokens for the Hub's own shell chrome — deliberately built from Frappe's existing
   semantic CSS variables (--control-bg, --border-color, --primary, ...) rather than a
   hand-rolled parallel light/dark palette, so the shell tracks Desk's theme automatically
   instead of drifting out of sync with it. */
:root {
	--egc-accent: var(--primary, var(--blue-500));
	--egc-accent-contrast: white;
}

/* Takes over the full Desk content area below the navbar (egc_project_hub.js hides the
   standard page-head bar) — Procore's own layout, top bar first (project/tool switcher), not a
   sidebar: a fixed-height flex COLUMN of [HubTopBar, HubHeader, scrollable content], not a page
   that grows and scrolls as a whole the way a themed DocType view does. */
.egc-shell {
	display: flex;
	flex-direction: column;
	/* `.layout-main-section` (this component's own mount point) is already sized by Frappe's
	   own layout CSS to exactly the space available below Desk's chrome — inheriting `100%` is
	   correct; independently subtracting `--navbar-height` here double-counts it. */
	height: 100%;
	background: var(--bg-color);
}

.egc-shell__content {
	flex: 1 1 auto;
	min-height: 0;
	overflow-y: auto;
	padding: 20px 24px 32px;
}

/* Shared table shell used by every register tab (WBS excluded — it renders a tree). Tables
   scroll horizontally within their own box instead of forcing the page to widen. */
.hub-table-wrap {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	overflow-x: auto;
	background: var(--fg-color);
}

.hub-table {
	width: 100%;
	border-collapse: collapse;
	font-size: var(--text-sm);
	min-width: 720px;
}

.hub-table th {
	text-align: left;
	padding: 10px 14px;
	font-weight: 600;
	color: var(--text-muted);
	border-bottom: 1px solid var(--border-color);
	white-space: nowrap;
	position: sticky;
	top: 0;
	background: var(--fg-color);
}

.hub-table td {
	padding: 10px 14px;
	border-bottom: 1px solid var(--border-color);
	color: var(--text-color);
	vertical-align: middle;
	/* Every current column is a bounded identifier/date/status, not free text — wrapping only
	   ever happened because the browser's automatic table layout squeezed a column narrower than
	   its content once some OTHER column (e.g. a long WBS label) demanded more room. Matching
	   `th`'s own nowrap here means a table that doesn't fit scrolls horizontally in its own box
	   (`.hub-table-wrap` already sets `overflow-x: auto`) instead of silently wrapping codes and
	   names across 2-3 lines. A genuinely long free-text column can opt back into wrapping with
	   its own `white-space: normal` override. */
	white-space: nowrap;
}

.hub-table tbody tr:last-child td {
	border-bottom: none;
}

.hub-table tbody tr.hub-table__row--clickable {
	cursor: pointer;
}

.hub-table tbody tr.hub-table__row--clickable:hover {
	background: var(--fg-hover-color, var(--control-bg));
}

.hub-table td.hub-table__overdue {
	color: var(--red-500, var(--text-on-red));
	font-weight: 500;
}

/* Opt-in for the one or two genuinely free-text columns a table has (a Name/Title) — caps how
   far an unusually long value can stretch the table, ellipsizing rather than wrapping. Hover
   still shows the full value via the native title tooltip. */
.hub-table__truncate {
	max-width: 260px;
	overflow: hidden;
	text-overflow: ellipsis;
}

/* Row-checkbox column — same fixed-width, no-wrap treatment in every table that has one. */
.hub-table__check-col {
	width: 34px;
	padding-left: 14px !important;
	padding-right: 0 !important;
}

/* Toolbar shared by filterable tabs */
.hub-toolbar {
	display: flex;
	flex-wrap: wrap;
	gap: 10px;
	margin-bottom: 12px;
	align-items: center;
}

.hub-toolbar select,
.hub-toolbar input[type="text"] {
	font-size: var(--text-sm);
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	color: var(--text-color);
	padding: 5px 8px;
	min-height: 30px;
}

.hub-toolbar input[type="text"] {
	min-width: 200px;
}

/* Section cards used by the Overview tab */
.hub-card {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	background: var(--fg-color);
	padding: 16px;
}

.hub-card__title {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
	margin-bottom: 12px;
}
</style>
