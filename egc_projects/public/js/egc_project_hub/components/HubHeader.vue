<!-- The Hub's slim top identity bar — everything that used to live in the old boxed
"HubHeader" card except the project switcher (now HubSidebar.vue, since switching projects is a
navigation act, not identity) and the stakeholder chips (now the Project Info tool's own job —
a header trying to show the full key-stakeholder list is exactly the "crammed form" look this
redesign moves away from; a name/status/stage/progress strip is what a persistent top bar in an
independent tool actually needs). -->
<script setup>
import { computed } from "vue";
import StatusPill from "./StatusPill.vue";
import QuickActions from "./QuickActions.vue";
import { useHubRoute } from "../composables/useHubRoute";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
	loading: { type: Boolean, default: false },
});
defineEmits(["toggle-sidebar"]);

const { setTab } = useHubRoute();

// ARCHITECTURE_V2.md §1: Project Information lives directly on `Project`'s own custom fields
// now, so `context.profile` is always a dict, never null — `has_profile_data` (not `profile`
// itself) is what distinguishes "nothing filled in yet" from a populated project, since every
// key still resolves to `undefined`/`""`/`[]` on a fresh Project either way.
const profile = computed(() => props.context?.profile || null);
const has_profile_data = computed(() => {
	const p = profile.value;
	if (!p) return false;
	return Boolean(p.project_code || p.project_stage || p.sector || p.key_stakeholders?.length);
});
const project_details_label = computed(() =>
	has_profile_data.value ? __("Project Details") : __("+ Add Project Information")
);

function open_form() {
	frappe.set_route("Form", "Project", props.project);
}

function goto_project_info() {
	setTab("project-info");
}

function format_date_range(dates) {
	if (!dates) return "";
	const { expected_start_date, expected_end_date } = dates;
	if (!expected_start_date && !expected_end_date) return "";
	const start = expected_start_date ? frappe.datetime.str_to_user(expected_start_date) : "?";
	const end = expected_end_date ? frappe.datetime.str_to_user(expected_end_date) : "?";
	return `${start} – ${end}`;
}
</script>

<template>
	<div class="egc-topbar">
		<button
			type="button"
			class="egc-topbar__menu-btn"
			:aria-label="__('Open navigation')"
			@click="$emit('toggle-sidebar')"
		>
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
				<path d="M3 6h18M3 12h18M3 18h18" />
			</svg>
		</button>

		<div class="egc-topbar__identity">
			<a class="egc-topbar__project-name" href="#" @click.prevent="open_form">
				{{ context ? context.project_name : project }}
			</a>
			<StatusPill v-if="context" :status="context.status" />

			<template v-if="context">
				<span v-if="context.customer" class="egc-topbar__sep">·</span>
				<span v-if="context.customer" class="egc-topbar__meta">{{ context.customer }}</span>
				<template v-if="profile && profile.project_stage">
					<span class="egc-topbar__sep">·</span>
					<span class="egc-topbar__meta">{{ __("Stage") }}: {{ profile.project_stage }}</span>
				</template>
				<template v-if="format_date_range(context.dates)">
					<span class="egc-topbar__sep">·</span>
					<span class="egc-topbar__meta">{{ format_date_range(context.dates) }}</span>
				</template>
			</template>
			<span v-else-if="loading" class="egc-topbar__meta egc-topbar__meta--loading">{{ __("Loading…") }}</span>
		</div>

		<div
			class="egc-topbar__complete"
			v-if="context && context.percent_complete !== null && context.percent_complete !== undefined"
		>
			<div class="egc-topbar__progress">
				<div class="egc-topbar__progress-bar" :style="{ width: (context.percent_complete || 0) + '%' }" />
			</div>
			<div class="egc-topbar__complete-value">{{ Math.round(context.percent_complete || 0) }}%</div>
		</div>

		<div class="egc-topbar__actions">
			<button
				v-if="context"
				type="button"
				class="btn btn-sm btn-default"
				:class="{ 'egc-topbar__profile-cta': !has_profile_data }"
				@click="goto_project_info"
			>
				{{ project_details_label }}
			</button>
			<QuickActions v-if="context" />
		</div>
	</div>
</template>

<style scoped>
.egc-topbar {
	display: flex;
	align-items: center;
	gap: 18px;
	padding: 12px 24px;
	border-bottom: 1px solid var(--border-color);
	background: var(--fg-color);
	flex-wrap: wrap;
}

.egc-topbar__identity {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 8px;
	flex: 1 1 320px;
	min-width: 0;
}

.egc-topbar__project-name {
	font-size: var(--text-md);
	font-weight: 600;
	color: var(--text-color);
}

.egc-topbar__project-name:hover {
	color: var(--text-color);
	text-decoration: underline;
}

.egc-topbar__meta {
	font-size: var(--text-sm);
	color: var(--text-muted);
	white-space: nowrap;
}

.egc-topbar__meta--loading {
	font-style: italic;
}

.egc-topbar__sep {
	color: var(--text-muted);
}

.egc-topbar__complete {
	display: flex;
	align-items: center;
	gap: 8px;
	flex: 0 0 160px;
}

.egc-topbar__progress {
	flex: 1;
	height: 6px;
	border-radius: var(--border-radius-full);
	background: var(--control-bg);
	overflow: hidden;
}

.egc-topbar__progress-bar {
	height: 100%;
	background: var(--dark-green-500, var(--green-500));
	border-radius: var(--border-radius-full);
}

.egc-topbar__complete-value {
	font-size: var(--text-xs);
	color: var(--text-muted);
	width: 34px;
	text-align: right;
}

.egc-topbar__actions {
	display: flex;
	align-items: center;
	gap: 8px;
	flex: 0 0 auto;
}

.egc-topbar__profile-cta {
	color: var(--text-muted);
	border-style: dashed;
}

.egc-topbar__menu-btn {
	display: none;
	appearance: none;
	border: none;
	background: none;
	cursor: pointer;
	padding: 4px;
	color: var(--text-color);
	flex: 0 0 auto;
}

.egc-topbar__menu-btn svg {
	width: 22px;
	height: 22px;
}

@media (max-width: 900px) {
	.egc-topbar__menu-btn {
		display: block;
	}
}
</style>
