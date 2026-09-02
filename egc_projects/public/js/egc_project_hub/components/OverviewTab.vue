<!-- Overview — the project's own front page. Redesigned to read as a professional status
     dashboard external parties (client, OEM reps like Siemens) can check on their own, not an
     internal admin screen: a hero identity/progress header, a Submittals spotlight (status
     breakdown + the actual most-urgent rows, not just a count), Key Contacts, then the existing
     Activities/Drawings/Recent Activity detail. Financials are deliberately never shown here —
     that stays gated behind the Financials tab's own role check, exactly as before. -->
<script setup>
import { computed, ref, watch } from "vue";
import { get_overview, get_my_open_items, get_submittals } from "../api";
import { useHubResource } from "../composables/useHubResource";
import { useHubRoute } from "../composables/useHubRoute";
import { overdueIntent } from "../composables/useOverdueIntent";
import { drawingsIntent } from "../composables/useDrawingsIntent";
import { openSubmittalIntent } from "../composables/useOpenSubmittalIntent";
import { openDocumentIntent } from "../composables/useOpenDocumentIntent";
import { openActivityIntent } from "../composables/useOpenActivityIntent";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});
const { setTab } = useHubRoute();

const { data, loading, error, reload } = useHubResource(() => get_overview(props.project));
const { data: open_items, loading: open_items_loading, reload: reload_open_items } = useHubResource(() =>
	get_my_open_items(props.project)
);
const { data: submittal_rows, loading: submittals_loading, reload: reload_submittals } = useHubResource(() =>
	get_submittals(props.project)
);

watch(() => props.project, reload, { immediate: true });
watch(() => props.project, reload_open_items, { immediate: true });
watch(() => props.project, reload_submittals, { immediate: true });

// -- Overview / My Tasks switch — a real tab, not a small buried card, so "what do I need to
// do" is as easy to find as the KPIs are (same VIEWS-switcher pattern ActivitiesTab.vue uses). --
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
// second round-trip for the image/description/stakeholders already sitting in context.
const profile = computed(() => props.context?.profile || {});
const has_profile_content = computed(() => Boolean(profile.value.project_image || profile.value.project_description));
const progress_pct = computed(() => Math.round(props.context?.percent_complete || 0));

// -- radial progress ring — plain SVG stroke-dasharray, no charting library needed for one value.
const RING_RADIUS = 30;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;
const ring_offset = computed(() => RING_CIRCUMFERENCE * (1 - progress_pct.value / 100));
const ring_tone = computed(() => {
	const health = data.value?.health?.schedule;
	if (health === "red") return "hub-ring--red";
	if (health === "orange") return "hub-ring--orange";
	return "hub-ring--green";
});

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

// Shared by My Tasks (open_item), Recent Activity, and the Submittals Spotlight — into the
// Hub's own Submittals/Documents/Activities tab-and-detail view, not the raw native form,
// matching SubmittalDetail.vue/DocumentDetail.vue's own cross-nav convention.
function open_related(doctype, name) {
	if (doctype === "EGC Submittal") {
		openSubmittalIntent.submittal = name;
		setTab("submittals");
	} else if (doctype === "EGC Project Document") {
		openDocumentIntent.document = name;
		setTab("documents");
	} else if (doctype === "EGC Activity") {
		openActivityIntent.activity = name;
		setTab("activities");
	} else {
		frappe.set_route("Form", doctype, name);
	}
}

function open_item(item) {
	open_related(item.doctype, item.name);
}

function open_submittal_row(row) {
	open_related("EGC Submittal", row.name);
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
	open_related(doctype, name);
}

// -- Submittals Spotlight: a real status breakdown bar (proportional, not just a legend) plus
// the actual most-pressing rows — overdue first, then nearest due date — so "what's going out
// and where does it stand" is answered without leaving Overview. -----------------------------

const SUBMITTAL_BAR_SEGMENTS = [
	{ key: "approved", label: __("Approved"), tone: "green" },
	{ key: "approved_with_comments", label: __("Approved w/ Comments"), tone: "blue" },
	{ key: "under_review", label: __("Under Review"), tone: "orange" },
	{ key: "revise_resubmit", label: __("Revise & Resubmit"), tone: "red" },
	{ key: "rejected", label: __("Rejected"), tone: "darkred" },
];

const submittal_breakdown = computed(() => {
	const s = data.value?.submittals;
	if (!s || !s.total) return [];
	return SUBMITTAL_BAR_SEGMENTS.map((seg) => ({
		...seg,
		count: s[seg.key] || 0,
		pct: ((s[seg.key] || 0) / s.total) * 100,
	})).filter((seg) => seg.count > 0);
});

// "Urgent" = not yet resolved — Approved and Approved with Comments are both closed states
// (comments there are advisory, not a blocking response), so neither belongs in a "needs
// attention" list even though they aren't literally "Approved".
const RESOLVED_STATUSES = ["Approved", "Approved with Comments"];

const urgent_submittals = computed(() => {
	const rows = submittal_rows.value || [];
	return [...rows]
		.filter((row) => !RESOLVED_STATUSES.includes(row.submittal_status))
		.sort((a, b) => {
			if (a.is_overdue !== b.is_overdue) return a.is_overdue ? -1 : 1;
			const ad = a.current_due_date || "9999-99-99";
			const bd = b.current_due_date || "9999-99-99";
			return ad < bd ? -1 : ad > bd ? 1 : 0;
		})
		.slice(0, 6);
});

// -- Key Contacts: who's actually on this project, for a party checking in from outside EGC. --
const key_contacts = computed(() => props.context?.profile?.key_stakeholders || []);

function initials(name) {
	if (!name) return "?";
	return name
		.split(/\s+/)
		.filter(Boolean)
		.slice(0, 2)
		.map((part) => part[0].toUpperCase())
		.join("");
}

// Hand-authored stroke icons, same visual language as HubTopBar.vue's own ICONS map (its
// comment explains why: "a distinct icon set is part of what makes this feel like its own
// product") — reused verbatim here rather than emoji, per direct user instruction.
const ENTRY_ICON_PATHS = {
	rev: '<path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 15.5h6M9 8.5h2"/>',
	sub: '<path d="M21 3 3 10.5l7 2.5m11-10L14 21l-4-8m11-10L10 13"/>',
	act: '<circle cx="12" cy="12" r="9"/><path d="m8.5 12.5 2.5 2.5 5-5"/>',
};

const CARD_ICON_PATHS = {
	activities: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
	submittals: '<path d="M21 3 3 10.5l7 2.5m11-10L14 21l-4-8m11-10L10 13"/>',
	drawings: '<path d="M4 4h16v16H4z"/><path d="M4 9h16M9 4v16"/>',
};

// Same icon set, for My Tasks' two item sources.
const TASK_ICON_PATHS = {
	activity_overdue: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
	submittal_review: '<path d="M21 3 3 10.5l7 2.5m11-10L14 21l-4-8m11-10L10 13"/>',
};

function task_icon(item) {
	return item.source === "activity_overdue" ? TASK_ICON_PATHS.activity_overdue : TASK_ICON_PATHS.submittal_review;
}

const recent_entries = computed(() => {
	if (!data.value) return [];
	const recent = data.value.recent;
	const entries = [
		...recent.document_revisions.map((row) => ({
			key: "rev:" + row.name,
			type: "rev",
			text: __("Revision {0} of {1}", [row.revision, row.document]),
			sub: row.revision_status,
			timestamp: row.modified,
			// The revision itself has no Hub detail view of its own — open the parent Document,
			// which shows every revision (including this one) in its own Revision Register.
			doctype: "EGC Project Document",
			name: row.document,
		})),
		...recent.submittal_responses.map((row) => ({
			key: "sub:" + row.name,
			type: "sub",
			text: __("{0} responded {1} for {2}", [row.responded_by || __("Reviewer"), row.response, row.submittal]),
			sub: row.revision_label,
			timestamp: row.response_date,
			// Same reasoning as document_revisions above — open the parent Submittal.
			doctype: "EGC Submittal",
			name: row.submittal,
		})),
		...recent.activity_updates.map((row) => ({
			key: "act:" + row.name,
			type: "act",
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
			<!-- Hero: identity + overall progress + health, in one glance for anyone checking in
			     from outside EGC. -->
			<div class="hub-card hub-hero">
				<img v-if="profile.project_image" :src="profile.project_image" class="hub-hero__image" :alt="context?.project_name" />
				<div class="hub-hero__body">
					<div class="hub-hero__top">
						<div class="hub-hero__name">{{ context?.project_name }}</div>
						<span v-if="context?.status" class="indicator-pill blue">{{ context.status }}</span>
					</div>
					<p v-if="profile.project_description" class="hub-hero__description">{{ profile.project_description }}</p>
					<div v-if="profile.project_stage || profile.sector" class="hub-hero__chips">
						<span v-if="profile.project_stage" class="hub-hero__chip">{{ profile.project_stage }}</span>
						<span v-if="profile.sector" class="hub-hero__chip">{{ profile.sector }}</span>
					</div>
					<div v-if="health_entries.length" class="hub-health__row">
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
				<div class="hub-hero__progress">
					<svg viewBox="0 0 72 72" class="hub-ring" :class="ring_tone">
						<circle class="hub-ring__track" cx="36" cy="36" r="30" />
						<circle
							class="hub-ring__value"
							cx="36"
							cy="36"
							r="30"
							:stroke-dasharray="RING_CIRCUMFERENCE"
							:stroke-dashoffset="ring_offset"
						/>
					</svg>
					<div class="hub-ring__text">
						<div class="hub-ring__pct">{{ progress_pct }}%</div>
						<div class="hub-ring__label">{{ __("Complete") }}</div>
					</div>
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
							<svg
								class="hub-recent__icon"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.8"
								stroke-linecap="round"
								stroke-linejoin="round"
								v-html="task_icon(item)"
							></svg>
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
			<!-- Submittals Spotlight — the section the user explicitly wanted to lead with:
			     status breakdown as a proportional bar, then the actual rows that need eyes. -->
			<div class="hub-card hub-spotlight">
				<div class="hub-card__title-row">
					<div class="hub-card__title">{{ __("Submittals") }}</div>
					<button type="button" class="hub-link-btn" @click="setTab('submittals')">{{ __("View all") }} →</button>
				</div>

				<template v-if="data.submittals.total">
					<div class="hub-bar">
						<div
							v-for="seg in submittal_breakdown"
							:key="seg.key"
							class="hub-bar__seg"
							:class="`hub-bar__seg--${seg.tone}`"
							:style="{ width: seg.pct + '%' }"
							:title="`${seg.label}: ${seg.count}`"
						></div>
					</div>
					<div class="hub-bar__legend">
						<span v-for="seg in submittal_breakdown" :key="seg.key" class="hub-bar__legend-item">
							<span class="hub-bar__dot" :class="`hub-bar__seg--${seg.tone}`"></span>
							{{ seg.label }} ({{ seg.count }})
						</span>
					</div>

					<LoadingState v-if="submittals_loading" :rows="3" />
					<EmptyState v-else-if="!urgent_submittals.length" :title="__('Nothing outstanding — every submittal is resolved.')" />
					<table v-else class="hub-submittal-table">
						<thead>
							<tr>
								<th>{{ __("Submittal") }}</th>
								<th>{{ __("Status") }}</th>
								<th>{{ __("Ball in Court") }}</th>
								<th>{{ __("Due") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in urgent_submittals" :key="row.name" @click="open_submittal_row(row)">
								<td>
									<div class="hub-submittal-table__number">{{ row.submittal_number }}</div>
									<div class="hub-submittal-table__title">{{ row.title }}</div>
								</td>
								<td><StatusPill :status="row.submittal_status" :overdue="row.is_overdue" /></td>
								<td class="hub-submittal-table__bic">{{ row.ball_in_court || "—" }}</td>
								<td class="hub-submittal-table__due">
									{{ row.current_due_date ? frappe.datetime.str_to_user(row.current_due_date) : "—" }}
								</td>
							</tr>
						</tbody>
					</table>
				</template>
				<EmptyState v-else :title="__('No submittals yet')" />
			</div>

			<div v-if="key_contacts.length" class="hub-card">
				<div class="hub-card__title">{{ __("Key Contacts") }}</div>
				<div class="hub-contacts">
					<div v-for="row in key_contacts" :key="row.role" class="hub-contact">
						<span class="hub-contact__avatar">{{ initials(row.party_name) }}</span>
						<div class="hub-contact__body">
							<div class="hub-contact__name">{{ row.party_name || "—" }}</div>
							<div class="hub-contact__role">{{ row.role }}<template v-if="row.organization"> · {{ row.organization }}</template></div>
						</div>
					</div>
				</div>
			</div>

			<div class="hub-overview__grid">
				<div class="hub-card hub-tile">
					<div class="hub-card__title-row">
						<div class="hub-card__title">{{ __("Activities") }}</div>
						<svg class="hub-card__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" v-html="CARD_ICON_PATHS.activities"></svg>
					</div>
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

				<div class="hub-card hub-tile">
					<div class="hub-card__title-row">
						<div class="hub-card__title">{{ __("Drawings") }}</div>
						<svg class="hub-card__icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" v-html="CARD_ICON_PATHS.drawings"></svg>
					</div>
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
						<svg
							class="hub-recent__icon"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="1.8"
							stroke-linecap="round"
							stroke-linejoin="round"
							v-html="ENTRY_ICON_PATHS[entry.type]"
						></svg>
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
.hub-hero {
	display: flex;
	align-items: center;
	gap: 20px;
	margin-bottom: 14px;
}

.hub-hero__image {
	width: 72px;
	height: 72px;
	border-radius: var(--border-radius-lg);
	object-fit: cover;
	border: 1px solid var(--border-color);
	flex: 0 0 auto;
}

.hub-hero__body {
	min-width: 0;
	flex: 1;
}

.hub-hero__top {
	display: flex;
	align-items: center;
	gap: 10px;
	flex-wrap: wrap;
}

.hub-hero__name {
	font-size: var(--text-xl);
	font-weight: 600;
	color: var(--text-color);
}

.hub-hero__description {
	margin: 4px 0 0;
	font-size: var(--text-sm);
	color: var(--text-muted);
	white-space: pre-wrap;
}

.hub-hero__chips {
	display: flex;
	gap: 6px;
	margin-top: 8px;
	flex-wrap: wrap;
}

.hub-hero__chip {
	font-size: var(--text-xs);
	font-weight: 500;
	color: var(--text-muted);
	background: var(--control-bg);
	border-radius: var(--border-radius-full);
	padding: 2px 10px;
}

.hub-hero__progress {
	flex: 0 0 auto;
	position: relative;
	width: 72px;
	height: 72px;
}

.hub-ring {
	width: 72px;
	height: 72px;
	transform: rotate(-90deg);
}

.hub-ring__track {
	fill: none;
	stroke: var(--control-bg);
	stroke-width: 6;
}

.hub-ring__value {
	fill: none;
	stroke-width: 6;
	stroke-linecap: round;
	transition: stroke-dashoffset 0.4s ease;
}

.hub-ring--green .hub-ring__value {
	stroke: var(--green-500, #2e7d32);
}

.hub-ring--orange .hub-ring__value {
	stroke: var(--orange-500, #ef8f2f);
}

.hub-ring--red .hub-ring__value {
	stroke: var(--red-500, #d1403d);
}

.hub-ring__text {
	position: absolute;
	inset: 0;
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
}

.hub-ring__pct {
	font-size: var(--text-md);
	font-weight: 700;
	color: var(--text-color);
	line-height: 1.1;
}

.hub-ring__label {
	font-size: 9px;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.03em;
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

.hub-health__row {
	display: flex;
	flex-wrap: wrap;
	gap: 18px;
	margin-top: 10px;
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

.hub-card__title-row {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 8px;
}

.hub-card__icon {
	width: 18px;
	height: 18px;
	color: var(--text-muted);
	flex: 0 0 auto;
}

.hub-link-btn {
	appearance: none;
	border: none;
	background: none;
	color: var(--text-muted);
	font-size: var(--text-xs);
	font-weight: 600;
	cursor: pointer;
	padding: 2px 4px;
}

.hub-link-btn:hover {
	color: var(--text-color);
	text-decoration: underline;
}

.hub-spotlight {
	margin-bottom: 14px;
}

.hub-bar {
	display: flex;
	height: 8px;
	border-radius: var(--border-radius-full);
	overflow: hidden;
	margin: 10px 0 6px;
	background: var(--control-bg);
}

.hub-bar__seg {
	height: 100%;
}

.hub-bar__seg--green {
	background: var(--green-500, #2e7d32);
}

.hub-bar__seg--blue {
	background: var(--blue-500, #2563eb);
}

.hub-bar__seg--orange {
	background: var(--orange-500, #ef8f2f);
}

.hub-bar__seg--red {
	background: var(--red-500, #d1403d);
}

.hub-bar__seg--darkred {
	background: #8f2323;
}

.hub-bar__legend {
	display: flex;
	flex-wrap: wrap;
	gap: 12px;
	margin-bottom: 12px;
}

.hub-bar__legend-item {
	display: flex;
	align-items: center;
	gap: 5px;
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.hub-bar__dot {
	width: 8px;
	height: 8px;
	border-radius: 50%;
	flex: 0 0 auto;
}

.hub-submittal-table {
	width: 100%;
	border-collapse: collapse;
	font-size: var(--text-sm);
}

.hub-submittal-table th {
	text-align: left;
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
	padding: 6px 8px;
	border-bottom: 1px solid var(--border-color);
}

.hub-submittal-table td {
	padding: 8px;
	border-bottom: 1px solid var(--border-color);
	vertical-align: top;
}

.hub-submittal-table tbody tr {
	cursor: pointer;
}

.hub-submittal-table tbody tr:hover {
	background: var(--control-bg);
}

.hub-submittal-table tbody tr:last-child td {
	border-bottom: none;
}

.hub-submittal-table__number {
	font-weight: 600;
	color: var(--text-color);
}

.hub-submittal-table__title {
	color: var(--text-muted);
	font-size: var(--text-xs);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	max-width: 260px;
}

.hub-submittal-table__bic,
.hub-submittal-table__due {
	color: var(--text-muted);
	white-space: nowrap;
}

.hub-contacts {
	display: flex;
	flex-wrap: wrap;
	gap: 16px;
	margin-top: 8px;
}

.hub-contact {
	display: flex;
	align-items: center;
	gap: 8px;
}

.hub-contact__avatar {
	width: 32px;
	height: 32px;
	border-radius: 50%;
	background: var(--control-bg);
	color: var(--text-color);
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: var(--text-xs);
	font-weight: 700;
	flex: 0 0 auto;
}

.hub-contact__name {
	font-size: var(--text-sm);
	color: var(--text-color);
	font-weight: 500;
}

.hub-contact__role {
	font-size: var(--text-xs);
	color: var(--text-muted);
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
	margin-top: 8px;
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
	gap: 12px;
	padding: 10px 6px;
	border-bottom: 1px solid var(--border-color);
	cursor: pointer;
	font-size: var(--text-sm);
	border-radius: var(--border-radius);
}

.hub-recent__item:last-child {
	border-bottom: none;
}

.hub-recent__item:hover {
	background: var(--control-bg);
}

.hub-recent__icon {
	flex: 0 0 auto;
	width: 28px;
	height: 28px;
	padding: 6px;
	box-sizing: border-box;
	border-radius: var(--border-radius-full);
	background: var(--control-bg);
	color: var(--text-muted);
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
