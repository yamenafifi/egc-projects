<script setup>
import { ref, computed, watch } from "vue";
import { useHubRoute, TABS } from "./composables/useHubRoute";
import { get_project_context } from "./api";
import HubHeader from "./components/HubHeader.vue";
import TabNav from "./components/TabNav.vue";
import ProjectPicker from "./components/ProjectPicker.vue";
import LoadingState from "./components/LoadingState.vue";
import ErrorState from "./components/ErrorState.vue";
import OverviewTab from "./components/OverviewTab.vue";
import WbsTab from "./components/WbsTab.vue";
import ActivitiesTab from "./components/ActivitiesTab.vue";
import SubmittalsTab from "./components/SubmittalsTab.vue";
import DrawingsTab from "./components/DrawingsTab.vue";
import FinancialsTab from "./components/FinancialsTab.vue";
// WP-10/WP-09 landed while this shell was in progress — wired straight in, no placeholder left.
import DocumentsTab from "./components/DocumentsTab.vue";
import ProjectInfoTab from "./components/ProjectInfoTab.vue";

defineProps({ page: { type: Object, default: null } });

const { route, setProject, setTab } = useHubRoute();

const TAB_LABELS = {
	overview: __("Overview"),
	wbs: __("WBS"),
	activities: __("Activities"),
	submittals: __("Submittals"),
	documents: __("Documents"),
	drawings: __("Drawings"),
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
		drawings: DrawingsTab,
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
	<div class="hub">
		<ProjectPicker v-if="!route.project" @select="setProject" />

		<template v-else>
			<HubHeader
				:project="route.project"
				:context="context"
				:loading="context_loading"
				@switch-project="setProject"
			/>

			<ErrorState v-if="context_error" :message="context_error" @retry="load_context" />

			<template v-else>
				<TabNav :tabs="tab_defs" :active="route.tab" @select="setTab" />

				<LoadingState v-if="context_loading && !context" :rows="6" />

				<component
					:is="tab_component"
					v-else-if="context"
					:key="route.tab + ':' + route.project"
					:project="route.project"
					:context="context"
				/>
			</template>
		</template>
	</div>
</template>

<style>
.hub {
	padding: 4px 2px 24px;
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
