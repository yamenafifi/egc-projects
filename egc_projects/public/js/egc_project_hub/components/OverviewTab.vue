<script setup>
import { computed, ref, watch } from "vue";
import { get_overview, get_my_open_items } from "../api";
import { useHubResource } from "../composables/useHubResource";
import { useHubRoute } from "../composables/useHubRoute";
import { overdueIntent } from "../composables/useOverdueIntent";
import { drawingsIntent } from "../composables/useDrawingsIntent";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});
const { setTab } = useHubRoute();

const { data, loading, error, reload } = useHubResource(() => get_overview(props.project));
const { data: open_items, loading: open_items_loading, reload: reload_open_items } = useHubResource(() =>
	get_my_open_items(props.project)
);

watch(() => props.project, reload, { immediate: true });
watch(() => props.project, reload_open_items, { immediate: true });

// -- Overview / My Tasks switch — a real tab, not a small buried card, so "what do I need to
// do" is as easy to find as the KPIs are (same VIEWS-switcher pattern ActivitiesTab.vue uses). --
const VIEWS = ["overview", "tasks"];
const active_view = ref("overview");

const task_count = computed(() => (open_items.value || []).length);

// Label says "Drawings", not "Documents" — the backend signal behind this key
// (_drawings_health in api/hub.py) only ever looks at drawings' review due dates, not every
// controlled document, so a label matching what it actually measures beats a generic one that
// implies more than it delivers.
const HEALTH_LABELS = {
	schedule: __("Schedule"),
	submittals: __("Submittals"),
	documents: __("Drawings"),
	financials: __("Financials"),
};

// What each color means, PER dimension — colors aren't a shared scale across dimensions (e.g.
// Financials only ever shows green/red, never orange), so a generic "red = bad" legend would be
// wrong for at least one of these. Mirrors the exact rules in api/hub.py's _schedule_health /
// _submittals_health / _drawings_health / _financials_health.
const HEALTH_TOOLTIPS = {
	schedule: {
		green: __("No overdue activities."),
		orange: __("Activities are overdue, but were updated in the last 14 days."),
		red: __("Activities are overdue and haven't been updated in over 14 days."),
	},
	submittals: {
		green: __("Nothing overdue or awaiting resubmission."),
		orange: __("At least one submittal needs resubmission (Rejected or Revise & Resubmit)."),
		red: __("At least one submittal is past its due date and still open."),
	},
	documents: {
		green: __("No drawings under review are past their due date."),
		orange: __("At least one drawing under review is past its due date."),
		red: __("At least one drawing under review is past its due date."),
	},
	financials: {
		green: __("Gross margin is not negative (or not yet tracked)."),
		red: __("Gross margin is negative."),
	},
};

const HEALTH_TARGET_TAB = {
	schedule: "activities",
	submittals: "submittals",
	documents: "documents",
	financials: "financials",
};

// Already fetched once per project by EgcProjectHub.vue and passed down as `context` — no
// second round-trip for the image/description already sitting in context.profile.
const profile = computed(() => props.context?.profile || {});
const has_profile_content = computed(() => Boolean(profile.value.project_image || profile.value.project_description));

const health_entries = computed(() => {
	if (!data.value?.health) return [];
	return Object.entries(data.value.health).map(([key, color]) => ({
		key,
		label: HEALTH_LABELS[key] || key,
		color,
		tooltip: (HEALTH_TOOLTIPS[key] || {})[color] || "",
	}));
});

function goto_health(key) {
	if (key === "schedule") return goto_overdue("activities");
	if (key === "submittals") return goto_overdue("submittals");
	setTab(HEALTH_TARGET_TAB[key] || key);
}

function open_item(item) {
	frappe.set_route("Form", item.doctype, item.name);
}

const has_any_data = computed(() => {
	if (!data.value) return false;
	return data.value.activities.total > 0 || data.value.submittals.total > 0 || data.value.drawings.total > 0;
});

function goto_overdue(section) {
	overdueIntent[section] = true;
	setTab(section);
}

function goto_approved_drawings() {
	drawingsIntent.approvalStatus = "Approved";
	setTab("documents");
}

function open_route(doctype, name) {
	frappe.set_route("Form", doctype, name);
}

const recent_entries = computed(() => {
	if (!data.value) return [];
	const recent = data.value.recent;
	const entries = [
		...recent.document_revisions.map((row) => ({
			key: "rev:" + row.name,
			icon: "🗎",
			text: __("Revision {0} of {1}", [row.revision, row.document]),
			sub: row.revision_status,
			timestamp: row.modified,
			doctype: "EGC Project Document Revision",
			name: row.name,
		})),
		...recent.submittal_responses.map((row) => ({
			key: "sub:" + row.name,
			icon: "📩",
			text: __("{0} responded {1} for {2}", [row.responded_by || __("Reviewer"), row.response, row.submittal]),
			sub: row.revision_label,
			timestamp: row.response_date,
			doctype: "EGC Submittal Revision",
			name: row.name,
		})),
		...recent.activity_updates.map((row) => ({
			key: "act:" + row.name,
			icon: "✓",
			text: __("{0} — {1}", [row.activity_code, row.activity_name]),
			sub: `${row.status} · ${Math.round(row.percent_complete || 0)}%`,
			timestamp: row.modified,
			doctype: "EGC Activity",
			name: row.name,
		})),
	];
	return entries
		.filter((entry) => entry.timestamp)
		.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
		.slice(0, 12);
});
</script>

<template>
	<div class="hub-overview">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />
		<EmptyState
			v-else-if="!has_any_data"
			:title="__('Nothing recorded yet')"
			:description="__('Once WBS, activities, submittals or drawings are added to this project, they will summarise here.')"
		/>

		<template v-else>
			<div v-if="has_profile_content" class="hub-card hub-profile">
				<img v-if="profile.project_image" :src="profile.project_image" class="hub-profile__image" :alt="context?.project_name" />
				<div class="hub-profile__body">
					<div class="hub-profile__name">{{ context?.project_name }}</div>
					<p v-if="profile.project_description" class="hub-profile__description">{{ profile.project_description }}</p>
				</div>
			</div>

			<div class="hub-view-switch">
				<button
					type="button"
					class="hub-view-switch__btn"
					:class="{ 'hub-view-switch__btn--active': active_view === 'overview' }"
					@click="active_view = 'overview'"
				>
					{{ __("Overview") }}
				</button>
				<button
					type="button"
					class="hub-view-switch__btn"
					:class="{ 'hub-view-switch__btn--active': active_view === 'tasks' }"
					@click="active_view = 'tasks'"
				>
					{{ __("My Tasks") }}
					<span v-if="task_count" class="hub-view-switch__badge">{{ task_count }}</span>
				</button>
			</div>

			<template v-if="active_view === 'tasks'">
				<div class="hub-card">
					<div class="hub-card__title">{{ __("My Tasks") }}</div>
					<LoadingState v-if="open_items_loading" :rows="4" />
					<EmptyState
						v-else-if="!(open_items || []).length"
						:title="__('Nothing on your plate right now')"
						:description="__('Submittals awaiting your review and your overdue activities will show up here.')"
					/>
					<ul v-else class="hub-recent">
						<li
							v-for="item in open_items"
							:key="item.source + ':' + item.name"
							class="hub-recent__item"
							@click="open_item(item)"
						>
							<span class="hub-recent__icon">{{ item.source === "activity_overdue" ? "⏱" : "📩" }}</span>
							<span class="hub-recent__text">{{ item.title }}</span>
							<span class="hub-recent__sub">
								{{ item.source === "activity_overdue" ? __("Overdue Activity") : __("Awaiting Your Review") }}
							</span>
							<span v-if="item.is_overdue" class="hub-open-items__overdue">{{ __("Overdue") }}</span>
							<span v-if="item.due_date" class="hub-recent__time">
								{{ frappe.datetime.str_to_user(item.due_date) }}
							</span>
						</li>
					</ul>
				</div>
			</template>

			<template v-else>
			<div v-if="health_entries.length" class="hub-card hub-health">
				<div class="hub-card__title">{{ __("Project Health") }}</div>
				<div class="hub-health__row">
					<button
						v-for="entry in health_entries"
						:key="entry.key"
						type="button"
						class="hub-health__item"
						:title="entry.tooltip"
						@click="goto_health(entry.key)"
					>
						<span class="hub-health__dot" :class="`hub-health__dot--${entry.color}`"></span>
						<span class="hub-health__label">{{ entry.label }}</span>
					</button>
				</div>
			</div>

			<div class="hub-overview__grid">
				<div class="hub-card">
					<div class="hub-card__title">{{ __("Activities") }}</div>
					<div class="hub-stats">
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.activities.total }}</div>
							<div class="hub-stat__label">{{ __("Total") }}</div>
						</div>
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.activities.completed }}</div>
							<div class="hub-stat__label">{{ __("Completed") }}</div>
						</div>
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.activities.in_progress }}</div>
							<div class="hub-stat__label">{{ __("In Progress") }}</div>
						</div>
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.activities.not_started }}</div>
							<div class="hub-stat__label">{{ __("Not Started") }}</div>
						</div>
						<div
							class="hub-stat hub-stat--overdue"
							:class="{ 'hub-stat--clickable': data.activities.overdue > 0 }"
							@click="data.activities.overdue > 0 && goto_overdue('activities')"
						>
							<div class="hub-stat__value">{{ data.activities.overdue }}</div>
							<div class="hub-stat__label">{{ __("Overdue") }}</div>
						</div>
					</div>
				</div>

				<div class="hub-card">
					<div class="hub-card__title">{{ __("Submittals") }}</div>
					<div class="hub-stats">
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.submittals.total }}</div>
							<div class="hub-stat__label">{{ __("Total") }}</div>
						</div>
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.submittals.approved }}</div>
							<div class="hub-stat__label">{{ __("Approved") }}</div>
						</div>
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.submittals.approved_with_comments }}</div>
							<div class="hub-stat__label">{{ __("Approved w/ Comments") }}</div>
						</div>
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.submittals.under_review }}</div>
							<div class="hub-stat__label">{{ __("Under Review") }}</div>
						</div>
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.submittals.revise_resubmit }}</div>
							<div class="hub-stat__label">{{ __("Revise & Resubmit") }}</div>
						</div>
						<div
							class="hub-stat hub-stat--overdue"
							:class="{ 'hub-stat--clickable': data.submittals.overdue > 0 }"
							@click="data.submittals.overdue > 0 && goto_overdue('submittals')"
						>
							<div class="hub-stat__value">{{ data.submittals.overdue }}</div>
							<div class="hub-stat__label">{{ __("Overdue") }}</div>
						</div>
					</div>
				</div>

				<div class="hub-card">
					<div class="hub-card__title">{{ __("Drawings") }}</div>
					<div class="hub-stats">
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.drawings.total }}</div>
							<div class="hub-stat__label">{{ __("Total") }}</div>
						</div>
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.drawings.issued }}</div>
							<div class="hub-stat__label">{{ __("Issued") }}</div>
						</div>
						<div class="hub-stat">
							<div class="hub-stat__value">{{ data.drawings.pending_review }}</div>
							<div class="hub-stat__label">{{ __("Pending Review") }}</div>
						</div>
						<div
							class="hub-stat"
							:class="{ 'hub-stat--clickable': data.drawings.approved > 0 }"
							@click="data.drawings.approved > 0 && goto_approved_drawings()"
						>
							<div class="hub-stat__value">{{ data.drawings.approved }}</div>
							<div class="hub-stat__label">{{ __("Approved") }}</div>
						</div>
					</div>
				</div>
			</div>

			<div class="hub-card hub-overview__recent">
				<div class="hub-card__title">{{ __("Recent Activity") }}</div>
				<EmptyState v-if="!recent_entries.length" :title="__('No recent activity')" />
				<ul v-else class="hub-recent">
					<li
						v-for="entry in recent_entries"
						:key="entry.key"
						class="hub-recent__item"
						@click="open_route(entry.doctype, entry.name)"
					>
						<span class="hub-recent__icon">{{ entry.icon }}</span>
						<span class="hub-recent__text">{{ entry.text }}</span>
						<span class="hub-recent__sub">{{ entry.sub }}</span>
						<span class="hub-recent__time" :title="frappe.datetime.str_to_user(entry.timestamp)">
							{{ frappe.datetime.prettyDate(entry.timestamp) }}
						</span>
					</li>
				</ul>
			</div>
		</template>
		</template>
	</div>
</template>

<style scoped>
.hub-profile {
	display: flex;
	align-items: center;
	gap: 16px;
	margin-bottom: 14px;
}

.hub-profile__image {
	width: 64px;
	height: 64px;
	border-radius: var(--border-radius-lg);
	object-fit: cover;
	border: 1px solid var(--border-color);
	flex: 0 0 auto;
}

.hub-profile__body {
	min-width: 0;
}

.hub-profile__name {
	font-size: var(--text-lg);
	font-weight: 600;
	color: var(--text-color);
}

.hub-profile__description {
	margin: 4px 0 0;
	font-size: var(--text-sm);
	color: var(--text-muted);
	white-space: pre-wrap;
}

.hub-view-switch {
	display: flex;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	overflow: hidden;
	width: fit-content;
	margin-bottom: 14px;
}

.hub-view-switch__btn {
	appearance: none;
	border: none;
	background: var(--fg-color);
	color: var(--text-muted);
	padding: 5px 12px;
	font-size: var(--text-sm);
	cursor: pointer;
	display: flex;
	align-items: center;
	gap: 6px;
}

.hub-view-switch__btn + .hub-view-switch__btn {
	border-left: 1px solid var(--border-color);
}

.hub-view-switch__btn:hover {
	color: var(--text-color);
}

.hub-view-switch__btn--active {
	background: var(--control-bg);
	color: var(--text-color);
	font-weight: 600;
}

.hub-view-switch__badge {
	font-size: var(--text-xs);
	color: var(--text-muted);
	background: var(--control-bg);
	border-radius: var(--border-radius-full);
	padding: 0 6px;
	min-width: 16px;
	text-align: center;
}

.hub-view-switch__btn--active .hub-view-switch__badge {
	background: var(--fg-color);
}

.hub-health {
	margin-bottom: 14px;
}

.hub-health__row {
	display: flex;
	flex-wrap: wrap;
	gap: 20px;
	margin-top: 6px;
}

.hub-health__item {
	appearance: none;
	border: none;
	background: none;
	padding: 4px 6px;
	margin: -4px -6px;
	border-radius: var(--border-radius);
	display: flex;
	align-items: center;
	gap: 6px;
	cursor: pointer;
}

.hub-health__item:hover {
	background: var(--control-bg);
}

.hub-health__dot {
	width: 10px;
	height: 10px;
	border-radius: 50%;
	flex: 0 0 auto;
}

.hub-health__dot--green {
	background: var(--green-500, #2e7d32);
}

.hub-health__dot--orange {
	background: var(--orange-500, #ef8f2f);
}

.hub-health__dot--red {
	background: var(--red-500, #d1403d);
}

.hub-health__label {
	font-size: var(--text-sm);
	color: var(--text-color);
}

.hub-open-items {
	margin-bottom: 14px;
}

.hub-open-items__overdue {
	flex: 0 0 auto;
	color: var(--red-500, var(--text-on-red));
	font-size: var(--text-xs);
	font-weight: 600;
}

.hub-overview__grid {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
	gap: 14px;
	margin-bottom: 14px;
}

.hub-stats {
	display: flex;
	flex-wrap: wrap;
	gap: 14px;
}

.hub-stat {
	min-width: 64px;
}

.hub-stat__value {
	font-size: var(--text-xl);
	font-weight: 600;
	color: var(--text-color);
}

.hub-stat__label {
	font-size: var(--text-xs);
	color: var(--text-muted);
	white-space: nowrap;
}

.hub-stat--overdue .hub-stat__value,
.hub-stat--overdue .hub-stat__label {
	color: var(--red-500, var(--text-on-red));
}

.hub-stat--clickable {
	cursor: pointer;
	border-radius: var(--border-radius);
}

.hub-stat--clickable:hover {
	text-decoration: underline;
}

.hub-recent {
	list-style: none;
	margin: 0;
	padding: 0;
	display: flex;
	flex-direction: column;
}

.hub-recent__item {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 8px 4px;
	border-bottom: 1px solid var(--border-color);
	cursor: pointer;
	font-size: var(--text-sm);
}

.hub-recent__item:last-child {
	border-bottom: none;
}

.hub-recent__item:hover {
	background: var(--control-bg);
}

.hub-recent__icon {
	flex: 0 0 auto;
}

.hub-recent__text {
	flex: 1;
	color: var(--text-color);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.hub-recent__sub {
	color: var(--text-muted);
	font-size: var(--text-xs);
	flex: 0 0 auto;
}

.hub-recent__time {
	color: var(--text-muted);
	font-size: var(--text-xs);
	flex: 0 0 auto;
	white-space: nowrap;
}
</style>
