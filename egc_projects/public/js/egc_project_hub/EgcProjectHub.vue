<script setup>
import { ref, computed, watch } from "vue";
import { useHubRoute, TABS } from "./composables/useHubRoute";
import { has_financial_access } from "./constants";
import { get_project_context } from "./api";
import HubHeader from "./components/HubHeader.vue";
import HubTopBar from "./components/HubTopBar.vue";
import ProjectPicker from "./components/ProjectPicker.vue";
import PortfolioDashboard from "./components/PortfolioDashboard.vue";
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

// Browser tab title — "Project Manager - {project}" once a project is loaded, plain "Project
// Manager" on the bare picker screen. `route.project` (the Project's own name/naming series,
// e.g. PROJ-####) IS its identity — there is no separate "project code" field in this app.
watch(
	() => route.project,
	(project) => {
		frappe.utils.set_title(project ? __("Project Manager - {0}", [project]) : __("Project Manager"));
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
		<PortfolioDashboard v-if="!route.project && has_financial_access()" @select="setProject" />
		<ProjectPicker v-else-if="!route.project" @select="setProject" />

		<template v-else>
			<HubTopBar
				:project="route.project"
				:project-name="context ? context.project_name : ''"
				:tabs="tab_defs"
				:active="route.tab"
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

/* MentionCommentBox.vue mounts Frappe's own comment control inside a real `.comment-box` div —
   Frappe's own class, deliberately, not a `hub-`-prefixed one of this app's (see that
   component's own template comment for why the exact class name matters). Nothing to add here:
   `.comment-box` is block-level by default and its parent (`.submittal-composer`/
   `.activity-composer`, both plain `width: 100%` blocks) already gives it the full row — and
   since `.comment-box` is Frappe's own class, used by every native desk Timeline, this
   stylesheet must never add a blanket rule for it here (this file's <style> is global, not
   scoped) or it would leak onto every other comment box in the whole system. */

/* CommentCard.vue / CommunicationCard.vue — shared by all three detail pages' activity feeds. */
.hub-comment-card {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	padding: 10px 12px;
}

.hub-comment-card__header {
	display: flex;
	align-items: center;
	gap: 6px;
	font-size: var(--text-sm);
	color: var(--text-color);
	flex-wrap: wrap;
}

.hub-comment-card__when {
	color: var(--text-muted);
	font-size: var(--text-xs);
}

.hub-comment-card__status {
	font-size: var(--text-xs);
}

.hub-comment-card__actions {
	margin-left: auto;
	display: flex;
	align-items: center;
	gap: 10px;
	font-size: var(--text-xs);
}

.hub-comment-card__menu {
	position: relative;
}

.hub-comment-card__menu-btn {
	background: none;
	border: none;
	cursor: pointer;
	color: var(--text-muted);
	padding: 0 4px;
	font-weight: 700;
	line-height: 1;
}

.hub-comment-card__menu-list {
	position: absolute;
	right: 0;
	top: 100%;
	z-index: 5;
	background: var(--fg-color);
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	box-shadow: var(--shadow-md, 0 2px 6px rgba(0, 0, 0, 0.12));
	min-width: 100px;
}

.hub-comment-card__menu-list button {
	display: block;
	width: 100%;
	text-align: left;
	padding: 6px 10px;
	background: none;
	border: none;
	cursor: pointer;
	color: var(--text-color);
	font-size: var(--text-sm);
}

.hub-comment-card__menu-list button:hover {
	background: var(--fg-hover-color, var(--control-bg));
}

.hub-comment-card__body {
	margin-top: 6px;
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: pre-wrap;
	word-break: break-word;
}

.hub-comment-card__email-meta {
	margin-top: 4px;
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.hub-comment-card__edit {
	margin-top: 6px;
}

.hub-comment-card__edit-actions {
	display: flex;
	gap: 6px;
	margin-top: 6px;
}
</style>
