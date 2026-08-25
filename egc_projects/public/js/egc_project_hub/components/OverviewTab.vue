<script setup>
import { computed, watch } from "vue";
import { get_overview } from "../api";
import { useHubResource } from "../composables/useHubResource";
import { useHubRoute } from "../composables/useHubRoute";
import { overdueIntent } from "../composables/useOverdueIntent";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});
const { setTab } = useHubRoute();

const { data, loading, error, reload } = useHubResource(() => get_overview(props.project));

watch(() => props.project, reload, { immediate: true });

const has_any_data = computed(() => {
	if (!data.value) return false;
	return data.value.activities.total > 0 || data.value.submittals.total > 0 || data.value.drawings.total > 0;
});

function goto_overdue(section) {
	overdueIntent[section] = true;
	setTab(section);
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
	</div>
</template>

<style scoped>
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
