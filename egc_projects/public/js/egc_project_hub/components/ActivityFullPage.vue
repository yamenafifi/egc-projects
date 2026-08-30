<!-- Activity full-page workspace — replaces the Activities list the same way SubmittalDetail.vue
     replaces the Submittals list (see that file for the pattern this mirrors): a status banner up
     top for "what's true right now", a single chronological timeline down the middle for
     "everything that has happened" on this Activity, and a sidebar for the standing facts that
     don't belong in a history feed (schedule, dependencies, sub-activities, linked Submittals/
     Documents, team).

     Unlike a Submittal, an Activity has no dedicated audit doctype — the timeline is assembled
     from Frappe's own Version log (get_activity_history, api/activities.py) plus comments plus
     the `creation`/`owner` now carried on every link/dependency/assignment row. `ActivityDetail.vue`
     (the drawer) stays the quick glance/edit surface; this is where the full picture lives. -->
<script setup>
import { computed, ref, watch } from "vue";
import {
	get_activity_detail,
	get_activity_history,
	add_dependency,
	remove_dependency,
	update_activity_progress,
	create_activity,
	update_activity_fields,
	link_activity_record,
	unlink_activity_record,
} from "./activities_api";
import { add_assignment, remove_assignment } from "./assignments_api";
import { get_comments, add_comment } from "./comments_api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";

const props = defineProps({
	activity: { type: String, required: true },
	project: { type: String, required: true },
	canWrite: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "changed", "open-activity"]);

const { data, loading, error, reload } = useHubResource(() => get_activity_detail(props.activity));
watch(() => props.activity, reload, { immediate: true });

const history_events = ref([]);
async function load_history() {
	try {
		history_events.value = await get_activity_history(props.activity);
	} catch (e) {
		history_events.value = [];
	}
}
watch(() => props.activity, load_history, { immediate: true });

function notify_changed() {
	emit("changed");
	reload();
	load_history();
}

function open_form() {
	frappe.set_route("Form", "EGC Activity", props.activity);
}

function open_activity(name) {
	// Re-targets this SAME page at a related activity (a dependency or a child row) instead of
	// stacking a second one — mirrors ActivityDetail.vue's identical behavior.
	emit("open-activity", name);
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

function format_datetime(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

// duration_days is an Int field with no nullable representation in Frappe — 0 is the documented
// "not computed" sentinel, never a real duration (activity_control.py).
function format_duration(value) {
	return value ? __("{0} days", [value]) : "—";
}

// -- one-line "what's true right now" summary, same convention as ActivityDetail.vue/
// SubmittalDetail.vue's next_step_text. ---------------------------------------------------------

const status_summary_text = computed(() => {
	const a = data.value?.activity;
	if (!a) return null;
	if (a.is_group) {
		return __("Group Activity — status and progress are derived from {0} child activit{1}.", [
			data.value.children.length,
			data.value.children.length === 1 ? "y" : "ies",
		]);
	}
	if (a.is_overdue) {
		const days = frappe.datetime.get_diff(frappe.datetime.get_today(), a.planned_end_date);
		return __("Overdue by {0} day{1} — planned finish was {2}.", [days, days === 1 ? "" : "s", format_date(a.planned_end_date)]);
	}
	if (a.status === "Completed") {
		return __("Completed{0}.", [a.actual_end_date ? __(" on {0}", [format_date(a.actual_end_date)]) : ""]);
	}
	if (a.status === "Cancelled") return __("Cancelled.");
	if (a.status === "On Hold") return __("On hold.");
	if (a.status === "In Progress") {
		return __("In progress — {0}% complete, planned finish {1}.", [
			Math.round(a.percent_complete || 0),
			format_date(a.planned_end_date),
		]);
	}
	return a.planned_start_date
		? __("Not started yet — planned to begin {0}.", [format_date(a.planned_start_date)])
		: __("Not started yet — no planned start date set.");
});

const banner_tone = computed(() => {
	const a = data.value?.activity;
	if (!a) return "grey";
	if (a.is_overdue) return "red";
	if (a.status === "Completed") return "green";
	if (a.status === "On Hold") return "orange";
	if (a.status === "In Progress") return "blue";
	return "grey";
});

// -- inline progress/status update, same interaction ActivityDetail.vue offers -------------------

const editing_progress = ref(false);
const progress_draft = ref(0);
const status_draft = ref("");
const saving_progress = ref(false);
const STATUS_OPTIONS = ["Not Started", "In Progress", "On Hold", "Completed", "Cancelled"];

function start_progress_edit() {
	progress_draft.value = data.value.activity.percent_complete || 0;
	status_draft.value = data.value.activity.status;
	editing_progress.value = true;
}

async function save_progress() {
	saving_progress.value = true;
	try {
		await update_activity_progress(props.activity, progress_draft.value, status_draft.value);
		editing_progress.value = false;
		notify_changed();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Update Progress"), message: e.message, indicator: "red" });
	} finally {
		saving_progress.value = false;
	}
}

// -- edit dialog (same fixed field set as ActivityDetail.vue) ------------------------------------

function open_edit_dialog() {
	const activity = data.value.activity;
	const fields = [
		{ fieldname: "activity_name", fieldtype: "Data", label: __("Activity Name"), default: activity.activity_name, reqd: 1 },
		{ fieldname: "wbs_node", fieldtype: "Link", label: __("WBS Node"), options: "EGC WBS Node", default: activity.wbs_node, get_query: () => ({ filters: { project: props.project } }) },
		{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline", default: activity.discipline },
		{ fieldname: "description", fieldtype: "Small Text", label: __("Description"), default: activity.description },
	];
	if (!activity.is_group) {
		fields.push(
			{ fieldname: "weight_pct", fieldtype: "Percent", label: __("Weight %"), default: activity.weight_pct },
			{ fieldname: "planned_start_date", fieldtype: "Date", label: __("Planned Start"), default: activity.planned_start_date },
			{ fieldname: "planned_end_date", fieldtype: "Date", label: __("Planned Finish"), default: activity.planned_end_date },
			{ fieldname: "forecast_start_date", fieldtype: "Date", label: __("Forecast Start"), default: activity.forecast_start_date },
			{ fieldname: "forecast_end_date", fieldtype: "Date", label: __("Forecast Finish"), default: activity.forecast_end_date },
			{ fieldname: "actual_start_date", fieldtype: "Date", label: __("Actual Start"), default: activity.actual_start_date },
			{ fieldname: "actual_end_date", fieldtype: "Date", label: __("Actual Finish"), default: activity.actual_end_date },
			{ fieldname: "is_milestone", fieldtype: "Check", label: __("Is Milestone"), default: activity.is_milestone }
		);
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Edit Activity"),
		fields,
		primary_action_label: __("Save"),
		primary_action(values) {
			update_activity_fields(props.activity, values)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Save"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

// -- People ---------------------------------------------------------------------------------------

const ASSIGNMENT_ROLES = ["Responsible", "Assignee", "Supervisor", "Consultant", "Reviewer", "Contractor", "Watcher"];

function open_add_assignment_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Person"),
		fields: [
			{ fieldname: "person", fieldtype: "Link", label: __("Person"), options: "Contact", description: __("Leave blank to assign a whole Organization with no specific individual named.") },
			{ fieldname: "organization", fieldtype: "Link", label: __("Organization"), options: "Customer", description: __("Defaults from the Person's own organization when one is picked above.") },
			{ fieldname: "assignment_role", fieldtype: "Select", label: __("Role on this Activity"), options: ASSIGNMENT_ROLES, default: "Responsible", reqd: 1 },
			{ fieldname: "is_primary", fieldtype: "Check", label: __("Primary") },
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			add_assignment("EGC Activity", props.activity, values.assignment_role, values.person, values.organization, values.remarks, Boolean(values.is_primary))
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Person"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_remove_assignment(row) {
	frappe.confirm(__("Remove {0} from this Activity?", [row.person_name || row.organization_name]), () => {
		remove_assignment(row.name).then(notify_changed).catch((e) => {
			frappe.msgprint({ title: __("Could Not Remove"), message: e.message, indicator: "red" });
		});
	});
}

// -- children (group activities only) -------------------------------------------------------------

function open_add_child_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Child Activity"),
		fields: [
			{ fieldname: "activity_code", fieldtype: "Data", label: __("Activity Code"), reqd: 1 },
			{ fieldname: "activity_name", fieldtype: "Data", label: __("Activity Name"), reqd: 1 },
			{ fieldname: "is_group", fieldtype: "Check", label: __("Is Group") },
			{ fieldname: "wbs_node", fieldtype: "Link", label: __("WBS Node"), options: "EGC WBS Node", default: data.value?.activity?.wbs_node, get_query: () => ({ filters: { project: props.project } }) },
			{ fieldname: "discipline", fieldtype: "Link", label: __("Discipline"), options: "EGC Discipline", default: data.value?.activity?.discipline },
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			create_activity({ ...values, project: props.project, parent_egc_activity: props.activity })
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Create Activity"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

// -- dependencies ------------------------------------------------------------------------------

const DEPENDENCY_TYPES = ["Finish-to-Start", "Start-to-Start", "Finish-to-Finish", "Start-to-Finish"];

function open_add_dependency_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Dependency"),
		fields: [
			{ fieldname: "direction", fieldtype: "Select", label: __("Direction"), options: [__("This activity depends on…"), __("…depends on this activity")], default: __("This activity depends on…"), reqd: 1 },
			{ fieldname: "other_activity", fieldtype: "Link", label: __("Activity"), options: "EGC Activity", reqd: 1, get_query: () => ({ filters: { project: props.project, name: ["!=", props.activity] } }) },
			{ fieldname: "dependency_type", fieldtype: "Select", label: __("Type"), options: DEPENDENCY_TYPES, default: "Finish-to-Start" },
			{ fieldname: "lag_days", fieldtype: "Int", label: __("Lag (Days)"), default: 0 },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			const forward = values.direction === __("This activity depends on…");
			const predecessor = forward ? values.other_activity : props.activity;
			const successor = forward ? props.activity : values.other_activity;
			add_dependency(predecessor, successor, values.dependency_type, values.lag_days)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Dependency"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_remove_dependency(name) {
	frappe.confirm(__("Remove this dependency?"), () => {
		remove_dependency(name).then(notify_changed).catch((e) => {
			frappe.msgprint({ title: __("Could Not Remove Dependency"), message: e.message, indicator: "red" });
		});
	});
}

// -- linked Submittals / Documents, as real tables (matching ActivityExpandPanel.vue's treatment,
// SubmittalDetail.vue's sidebar Documents card, and the main Submittals/Documents registers) -----

const submittal_links = computed(() => (data.value?.links || []).filter((row) => row.link_doctype === "EGC Submittal"));
const document_links = computed(() => (data.value?.links || []).filter((row) => row.link_doctype === "EGC Project Document"));

const SUBMISSION_OPEN_STATUSES = ["Submitted", "Under Review"];
function is_submittal_overdue(row) {
	if (!row.current_due_date) return false;
	if (!SUBMISSION_OPEN_STATUSES.includes(row.submittal_status)) return false;
	return frappe.datetime.get_diff(row.current_due_date, frappe.datetime.get_today()) < 0;
}

function open_submittal(row) {
	frappe.set_route("Form", "EGC Submittal", row.link_name);
}

function open_document(row) {
	frappe.set_route("Form", "EGC Project Document", row.link_name);
}

function open_add_submittal_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Link Submittal"),
		fields: [
			{ fieldname: "link_name", fieldtype: "Link", label: __("Submittal"), options: "EGC Submittal", reqd: 1, get_query: () => ({ filters: { project: props.project } }) },
			{ fieldname: "link_purpose", fieldtype: "Select", label: __("Purpose"), options: ["Reference", "Requirement"], default: "Reference" },
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			link_activity_record(props.activity, "EGC Submittal", values.link_name, values.link_purpose, values.remarks)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Link"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function open_add_document_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Link Document"),
		fields: [
			{ fieldname: "link_name", fieldtype: "Link", label: __("Document"), options: "EGC Project Document", reqd: 1, get_query: () => ({ filters: { project: props.project } }) },
			{ fieldname: "link_purpose", fieldtype: "Select", label: __("Purpose"), options: ["Reference", "Requirement"], default: "Reference" },
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			link_activity_record(props.activity, "EGC Project Document", values.link_name, values.link_purpose, values.remarks)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => {
					frappe.msgprint({ title: __("Could Not Add Link"), message: e.message, indicator: "red" });
				});
		},
	});
	dialog.show();
}

function confirm_remove_link(row) {
	frappe.confirm(__("Remove this link?"), () => {
		unlink_activity_record(row.name).then(notify_changed).catch((e) => {
			frappe.msgprint({ title: __("Could Not Remove Link"), message: e.message, indicator: "red" });
		});
	});
}

// -- comments (generic thread — comments.py's only gate is read access to the Activity itself) --

const comments = ref([]);
const new_comment = ref("");
const posting_comment = ref(false);

async function load_comments() {
	try {
		comments.value = await get_comments("EGC Activity", props.activity);
	} catch (e) {
		comments.value = [];
	}
}
watch(() => props.activity, load_comments, { immediate: true });

async function do_post_comment() {
	if (!new_comment.value.trim()) return;
	posting_comment.value = true;
	try {
		await add_comment("EGC Activity", props.activity, new_comment.value);
		new_comment.value = "";
		await load_comments();
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Post Comment"), message: e.message, indicator: "red" });
	} finally {
		posting_comment.value = false;
	}
}

// -- unified timeline: everything that happened, merged and sorted by real timestamp — every
// event type here (Version-derived field changes, comments, and now link/dependency/assignment
// rows) carries a genuine Datetime `creation`, unlike SubmittalDetail.vue's timeline, which had
// to work around several Date-only fields. Plain chronological sort is enough. ------------------

const STATUS_TONE = { Completed: "green", Cancelled: "grey", "On Hold": "orange", "In Progress": "blue", "Not Started": "grey" };
const STATUS_ICON = { Completed: "✓", Cancelled: "✕", "On Hold": "‖", "In Progress": "↑", "Not Started": "○" };

function history_status_change(event) {
	return event.changes.find((c) => c.field === "status");
}

function event_tone(event) {
	if (event.type === "history") {
		const status_change = history_status_change(event);
		return status_change ? STATUS_TONE[status_change.to] || "grey" : "blue";
	}
	if (event.type === "comment") return "grey";
	return "grey";
}

function event_icon(event) {
	if (event.type === "created") return "+";
	if (event.type === "history") {
		const status_change = history_status_change(event);
		return status_change ? STATUS_ICON[status_change.to] || "○" : "✎";
	}
	if (event.type === "link" || event.type === "dependency" || event.type === "assignment") return "+";
	if (event.type === "comment") return "●";
	return "○";
}

const timeline_events = computed(() => {
	const events = [];

	if (data.value?.activity) {
		events.push({
			type: "created",
			key: "created",
			timestamp: data.value.activity.creation,
			owner: data.value.activity.owner,
		});
	}

	for (const ev of history_events.value) {
		events.push({ type: "history", key: ev.name, timestamp: ev.creation, owner: ev.owner, changes: ev.changes });
	}

	for (const row of data.value?.links || []) {
		events.push({ type: "link", key: `link-${row.name}`, timestamp: row.creation, owner: row.owner, row });
	}

	for (const dep of data.value?.dependencies?.predecessors || []) {
		events.push({ type: "dependency", key: `dep-${dep.name}`, timestamp: dep.creation, owner: dep.owner, dep, direction: "predecessor" });
	}
	for (const dep of data.value?.dependencies?.successors || []) {
		events.push({ type: "dependency", key: `dep-${dep.name}`, timestamp: dep.creation, owner: dep.owner, dep, direction: "successor" });
	}

	for (const row of data.value?.assignments || []) {
		events.push({ type: "assignment", key: `assign-${row.name}`, timestamp: row.creation, owner: row.owner, row });
	}

	for (const c of comments.value) {
		events.push({ type: "comment", key: `comment-${c.name}`, timestamp: c.creation, owner: c.owner, comment: c });
	}

	return events.filter((e) => e.timestamp).sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
});
</script>

<template>
	<div class="activity-page">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />

		<template v-else-if="data">
			<div class="activity-page__topbar">
				<a href="#" class="hub-link activity-page__back" @click.prevent="$emit('close')">
					{{ __("← Back to Activities") }}
				</a>
				<div class="activity-page__topbar-actions">
					<a v-if="canWrite" href="#" class="hub-link" @click.prevent="open_edit_dialog">{{ __("Edit") }}</a>
					<a href="#" class="hub-link hub-link--muted" @click.prevent="open_form">
						{{ __("View raw record ↗") }}
					</a>
				</div>
			</div>

			<div class="activity-page__identity">
				<div class="activity-page__code">{{ data.activity.activity_code }}</div>
				<h1 class="activity-page__title">{{ data.activity.activity_name }}</h1>
				<div class="activity-page__status-row">
					<StatusPill :status="data.activity.status" />
					<span v-if="data.activity.is_overdue" class="indicator-pill red">{{ __("Overdue") }}</span>
					<span v-if="data.activity.is_milestone" class="indicator-pill blue">{{ __("Milestone") }}</span>
					<span v-if="data.activity.is_group" class="indicator-pill gray">{{ __("Group") }}</span>
					<span class="activity-page__meta-inline">
						{{ data.activity.discipline || "—" }}<template v-if="data.activity.wbs_node"> · {{ data.activity.wbs_node }}</template>
					</span>
				</div>
			</div>

			<div class="activity-banner" :class="`activity-banner--${banner_tone}`">
				<div class="activity-banner__main">
					<p class="activity-banner__text">{{ status_summary_text }}</p>
					<div v-if="!data.activity.is_group" class="activity-banner__progress">
						<div class="hub-percent">
							<div class="hub-percent__track">
								<div class="hub-percent__fill" :style="{ width: (data.activity.percent_complete || 0) + '%' }" />
							</div>
							<span class="hub-percent__value">{{ Math.round(data.activity.percent_complete || 0) }}%</span>
						</div>
					</div>
				</div>
				<div v-if="canWrite && !data.activity.is_group" class="activity-banner__actions">
					<template v-if="editing_progress">
						<input v-model.number="progress_draft" type="number" min="0" max="100" step="1" class="activity-banner__progress-input" />
						<select v-model="status_draft" class="activity-banner__status-select">
							<option v-for="s in STATUS_OPTIONS" :key="s" :value="s">{{ s }}</option>
						</select>
						<button type="button" class="btn btn-sm btn-primary" :disabled="saving_progress" @click="save_progress">{{ __("Save") }}</button>
						<button type="button" class="btn btn-sm btn-default" @click="editing_progress = false">{{ __("Cancel") }}</button>
					</template>
					<button v-else type="button" class="btn btn-sm btn-primary" @click="start_progress_edit">{{ __("Update Progress") }}</button>
				</div>
			</div>

			<div class="activity-page__body">
				<div class="activity-main">
					<div class="activity-timeline">
						<EmptyState v-if="!timeline_events.length" :title="__('Nothing recorded yet')" />
						<div v-for="event in timeline_events" :key="event.key" class="activity-timeline__row">
							<div class="activity-timeline__rail">
								<span class="activity-timeline__dot" :class="`activity-timeline__dot--${event_tone(event)}`">
									{{ event_icon(event) }}
								</span>
								<span class="activity-timeline__line" />
							</div>

							<div class="activity-timeline__content">
								<template v-if="event.type === 'created'">
									<p class="activity-timeline__headline">
										{{ __("Activity created") }}
										<span v-if="event.owner" class="activity-timeline__by">— {{ event.owner }}</span>
										<span class="activity-timeline__when">{{ format_datetime(event.timestamp) }}</span>
									</p>
								</template>

								<template v-else-if="event.type === 'history'">
									<p class="activity-timeline__headline">
										{{ __("Updated") }}
										<span v-if="event.owner" class="activity-timeline__by">— {{ event.owner }}</span>
										<span class="activity-timeline__when">{{ format_datetime(event.timestamp) }}</span>
									</p>
									<ul class="activity-timeline__changes">
										<li v-for="change in event.changes" :key="change.field">
											<strong>{{ change.label }}:</strong> {{ change.from ?? "—" }} → {{ change.to ?? "—" }}
										</li>
									</ul>
								</template>

								<template v-else-if="event.type === 'link'">
									<p class="activity-timeline__headline">
										{{ __("Linked {0}", [event.row.link_doctype === "EGC Submittal" ? __("Submittal") : __("Document")]) }}:
										<strong>{{ event.row.link_title || event.row.link_name }}</strong>
										<span v-if="event.owner" class="activity-timeline__by">— {{ event.owner }}</span>
										<span class="activity-timeline__when">{{ format_datetime(event.timestamp) }}</span>
									</p>
								</template>

								<template v-else-if="event.type === 'dependency'">
									<p class="activity-timeline__headline">
										{{ event.direction === "predecessor" ? __("Dependency added — waits on") : __("Dependency added — blocks") }}
										<a href="#" class="hub-link" @click.prevent="open_activity(event.dep.activity)">
											{{ event.dep.activity_code }}: {{ event.dep.activity_name }}
										</a>
										<span v-if="event.owner" class="activity-timeline__by">— {{ event.owner }}</span>
										<span class="activity-timeline__when">{{ format_datetime(event.timestamp) }}</span>
									</p>
								</template>

								<template v-else-if="event.type === 'assignment'">
									<p class="activity-timeline__headline">
										{{ __("Added to Team") }}: <strong>{{ event.row.person_name || event.row.organization_name }}</strong>
										<span class="activity-timeline__role">({{ event.row.assignment_role }})</span>
										<span v-if="event.owner" class="activity-timeline__by">— {{ event.owner }}</span>
										<span class="activity-timeline__when">{{ format_datetime(event.timestamp) }}</span>
									</p>
								</template>

								<template v-else-if="event.type === 'comment'">
									<p class="activity-timeline__headline">
										<strong>{{ event.owner }}</strong> {{ __("commented") }}
										<span class="activity-timeline__when">{{ format_datetime(event.timestamp) }}</span>
									</p>
									<p class="activity-timeline__remarks">{{ event.comment.content }}</p>
								</template>
							</div>
						</div>
					</div>

					<div class="activity-composer">
						<textarea v-model="new_comment" class="form-control" rows="2" :placeholder="__('Add a comment…')"></textarea>
						<button type="button" class="btn btn-sm btn-primary" :disabled="posting_comment || !new_comment.trim()" @click="do_post_comment">
							{{ __("Post") }}
						</button>
					</div>
				</div>

				<div class="activity-sidebar">
					<div class="activity-sidebar__card">
						<div class="activity-detail__section-title">{{ __("Schedule") }}</div>
						<dl class="activity-detail__meta activity-sidebar__meta">
							<div>
								<dt>{{ __("Planned Start") }}</dt>
								<dd>{{ format_date(data.activity.planned_start_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Planned Finish") }}</dt>
								<dd>{{ format_date(data.activity.planned_end_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Duration") }}</dt>
								<dd>{{ format_duration(data.activity.duration_days) }}</dd>
							</div>
							<div>
								<dt>{{ __("Actual Start") }}</dt>
								<dd>{{ format_date(data.activity.actual_start_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Actual Finish") }}</dt>
								<dd>{{ format_date(data.activity.actual_end_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Forecast Start") }}</dt>
								<dd>{{ format_date(data.activity.forecast_start_date) }}</dd>
							</div>
							<div>
								<dt>{{ __("Forecast Finish") }}</dt>
								<dd>{{ format_date(data.activity.forecast_end_date) }}</dd>
							</div>
							<div v-if="!data.activity.is_group">
								<dt>{{ __("Weight %") }}</dt>
								<dd>{{ data.activity.weight_pct ? `${data.activity.weight_pct}%` : "—" }}</dd>
							</div>
						</dl>
						<p v-if="data.activity.is_group" class="activity-detail__derived-note">
							{{ __("Derived from children — cannot be edited directly.") }}
						</p>
						<p v-if="data.activity.description" class="activity-page__description">{{ data.activity.description }}</p>
					</div>

					<div class="activity-sidebar__card">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Submittals") }}</div>
							<button v-if="canWrite && !data.activity.is_group" type="button" class="btn btn-xs btn-default" @click="open_add_submittal_dialog">
								{{ __("Link Existing") }}
							</button>
						</div>
						<EmptyState v-if="!submittal_links.length" :title="data.activity.is_group ? __('Not applicable to a Group Activity') : __('No linked submittals yet')" />
						<div v-else class="hub-table-wrap">
							<table class="hub-table">
								<thead>
									<tr>
										<th>{{ __("Submittal No") }}</th>
										<th>{{ __("Title") }}</th>
										<th>{{ __("Status") }}</th>
										<th>{{ __("Ball in Court") }}</th>
										<th>{{ __("Due Date") }}</th>
										<th v-if="canWrite"></th>
									</tr>
								</thead>
								<tbody>
									<tr v-for="row in submittal_links" :key="row.name" class="hub-table__row--clickable" @click="open_submittal(row)">
										<td>{{ row.submittal_number || "—" }}</td>
										<td class="hub-table__truncate" :title="row.link_title">{{ row.link_title || "—" }}</td>
										<td><StatusPill :status="row.submittal_status" /></td>
										<td>{{ row.ball_in_court || "—" }}</td>
										<td :class="{ 'hub-table__overdue': is_submittal_overdue(row) }">
											{{ format_date(row.current_due_date) }}
											<span v-if="is_submittal_overdue(row)" class="hub-table__overdue-tag">{{ __("Overdue") }}</span>
										</td>
										<td v-if="canWrite">
											<button type="button" class="btn btn-xs btn-default" @click.stop="confirm_remove_link(row)">{{ __("Remove") }}</button>
										</td>
									</tr>
								</tbody>
							</table>
						</div>
					</div>

					<div class="activity-sidebar__card">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Drawings & Documents") }}</div>
							<button v-if="canWrite && !data.activity.is_group" type="button" class="btn btn-xs btn-default" @click="open_add_document_dialog">
								{{ __("Link Existing") }}
							</button>
						</div>
						<EmptyState v-if="!document_links.length" :title="data.activity.is_group ? __('Not applicable to a Group Activity') : __('No linked documents yet')" />
						<div v-else class="hub-table-wrap">
							<table class="hub-table">
								<thead>
									<tr>
										<th>{{ __("Document No") }}</th>
										<th>{{ __("Title") }}</th>
										<th>{{ __("Current Revision") }}</th>
										<th>{{ __("Status") }}</th>
										<th v-if="canWrite"></th>
									</tr>
								</thead>
								<tbody>
									<tr v-for="row in document_links" :key="row.name" class="hub-table__row--clickable" @click="open_document(row)">
										<td>{{ row.document_number || "—" }}</td>
										<td class="hub-table__truncate" :title="row.link_title">{{ row.link_title || "—" }}</td>
										<td>{{ row.current_revision_label || "—" }}</td>
										<td><StatusPill :status="row.approval_status" /></td>
										<td v-if="canWrite">
											<button type="button" class="btn btn-xs btn-default" @click.stop="confirm_remove_link(row)">{{ __("Remove") }}</button>
										</td>
									</tr>
								</tbody>
							</table>
						</div>
					</div>

					<div class="activity-sidebar__card">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Dependencies") }}</div>
							<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_add_dependency_dialog">
								{{ __("Add") }}
							</button>
						</div>
						<div class="activity-detail__dep-group">
							<div class="activity-detail__dep-label">{{ __("Predecessors") }}</div>
							<EmptyState v-if="!data.dependencies.predecessors.length" :title="__('None')" />
							<ul v-else class="activity-detail__list">
								<li v-for="dep in data.dependencies.predecessors" :key="dep.name">
									<a href="#" class="activity-detail__link" @click.prevent="open_activity(dep.activity)">
										{{ dep.activity_code }}: {{ dep.activity_name }}
									</a>
									<div class="activity-links__meta">
										<StatusPill :status="dep.status" />
										<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="confirm_remove_dependency(dep.name)">{{ __("Remove") }}</button>
									</div>
								</li>
							</ul>
						</div>
						<div class="activity-detail__dep-group">
							<div class="activity-detail__dep-label">{{ __("Successors") }}</div>
							<EmptyState v-if="!data.dependencies.successors.length" :title="__('None')" />
							<ul v-else class="activity-detail__list">
								<li v-for="dep in data.dependencies.successors" :key="dep.name">
									<a href="#" class="activity-detail__link" @click.prevent="open_activity(dep.activity)">
										{{ dep.activity_code }}: {{ dep.activity_name }}
									</a>
									<div class="activity-links__meta">
										<StatusPill :status="dep.status" />
										<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="confirm_remove_dependency(dep.name)">{{ __("Remove") }}</button>
									</div>
								</li>
							</ul>
						</div>
					</div>

					<div v-if="data.activity.is_group" class="activity-sidebar__card">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Sub-Activities") }}</div>
							<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_add_child_dialog">{{ __("Add") }}</button>
						</div>
						<EmptyState v-if="!data.children.length" :title="__('No child activities yet')" />
						<ul v-else class="activity-detail__list">
							<li v-for="child in data.children" :key="child.name">
								<a href="#" class="activity-detail__link" @click.prevent="open_activity(child.name)">
									{{ child.activity_code }}: {{ child.activity_name }}
									<span v-if="child.is_milestone" class="activity-detail__milestone-dot" :title="__('Milestone')" />
								</a>
								<div class="activity-links__meta">
									<StatusPill :status="child.status" />
									<span class="activity-detail__dep-type">{{ Math.round(child.percent_complete || 0) }}%</span>
								</div>
							</li>
						</ul>
					</div>

					<div class="activity-sidebar__card">
						<div class="activity-detail__head-row">
							<div class="activity-detail__section-title">{{ __("Team") }}</div>
							<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="open_add_assignment_dialog">{{ __("Add") }}</button>
						</div>
						<EmptyState v-if="!data.assignments.length" :title="__('No one assigned yet')" />
						<ul v-else class="activity-detail__list">
							<li v-for="row in data.assignments" :key="row.name">
								<div>
									<span class="activity-detail__link">{{ row.person_name || row.organization_name || __("Unnamed") }}</span>
									<span v-if="row.is_primary" class="indicator-pill blue">{{ __("Primary") }}</span>
								</div>
								<div class="activity-links__meta">
									<span class="activity-detail__dep-type">{{ row.assignment_role }}</span>
									<button v-if="canWrite" type="button" class="btn btn-xs btn-default" @click="confirm_remove_assignment(row)">{{ __("Remove") }}</button>
								</div>
							</li>
						</ul>
					</div>
				</div>
			</div>
		</template>
	</div>
</template>

<style scoped>
.activity-page {
	display: flex;
	flex-direction: column;
	gap: 18px;
}

.activity-page__topbar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
}

.activity-page__back {
	font-weight: 500;
}

.activity-page__topbar-actions {
	display: flex;
	align-items: center;
	gap: 14px;
}

.hub-link--muted {
	color: var(--text-muted);
	font-size: var(--text-xs);
}

.activity-page__identity {
	border-bottom: 1px solid var(--border-color);
	padding-bottom: 16px;
}

.activity-page__code {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-muted);
}

.activity-page__title {
	font-size: var(--text-2xl, 22px);
	font-weight: 600;
	color: var(--text-color);
	margin: 2px 0 10px;
}

.activity-page__status-row {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 8px 12px;
}

.activity-page__meta-inline {
	font-size: var(--text-sm);
	color: var(--text-muted);
}

.activity-page__description {
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: pre-wrap;
	margin: 12px 0 0;
}

.activity-banner {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	flex-wrap: wrap;
	gap: 10px 16px;
	border: 1px solid var(--border-color);
	border-left: 4px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 14px 16px;
	background: var(--subtle-fg, var(--control-bg));
}

.activity-banner--green {
	border-left-color: var(--green-500, #2e7d32);
}

.activity-banner--red {
	border-left-color: var(--red-500, #d1483e);
}

.activity-banner--orange {
	border-left-color: var(--orange-500, #d98c26);
}

.activity-banner--blue {
	border-left-color: var(--blue-500, #2f6fed);
}

.activity-banner__main {
	flex: 1 1 320px;
}

.activity-banner__text {
	margin: 0;
	font-size: var(--text-sm);
	color: var(--text-color);
}

.activity-banner__progress {
	margin-top: 10px;
	max-width: 260px;
}

.activity-banner__actions {
	display: flex;
	align-items: center;
	gap: 8px;
	flex: 0 0 auto;
	flex-wrap: wrap;
}

.activity-banner__progress-input {
	width: 64px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	color: var(--text-color);
	padding: 4px 8px;
}

.activity-banner__status-select {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	color: var(--text-color);
	padding: 4px 8px;
}

.activity-page__body {
	display: grid;
	grid-template-columns: minmax(0, 1fr) 300px;
	gap: 28px;
	align-items: start;
}

@media (max-width: 900px) {
	.activity-page__body {
		grid-template-columns: 1fr;
	}
}

.activity-main {
	min-width: 0;
}

.activity-timeline {
	display: flex;
	flex-direction: column;
}

.activity-timeline__row {
	display: flex;
	gap: 12px;
}

.activity-timeline__rail {
	display: flex;
	flex-direction: column;
	align-items: center;
	flex: 0 0 auto;
}

.activity-timeline__dot {
	width: 24px;
	height: 24px;
	flex: 0 0 auto;
	border-radius: 50%;
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: 12px;
	font-weight: 700;
	background: var(--control-bg);
	color: var(--text-muted);
	border: 1px solid var(--border-color);
}

.activity-timeline__dot--green {
	color: var(--green-500, #2e7d32);
	border-color: var(--green-200, var(--green-500, #2e7d32));
}

.activity-timeline__dot--red {
	color: var(--red-500, #d1483e);
	border-color: var(--red-200, var(--red-500, #d1483e));
}

.activity-timeline__dot--orange {
	color: var(--orange-500, #d98c26);
	border-color: var(--orange-200, var(--orange-500, #d98c26));
}

.activity-timeline__dot--blue {
	color: var(--blue-500, #2f6fed);
	border-color: var(--blue-200, var(--blue-500, #2f6fed));
}

.activity-timeline__line {
	flex: 1 1 auto;
	width: 1px;
	background: var(--border-color);
	min-height: 12px;
}

.activity-timeline__row:last-child .activity-timeline__line {
	display: none;
}

.activity-timeline__content {
	flex: 1 1 auto;
	min-width: 0;
	padding-bottom: 20px;
}

.activity-timeline__headline {
	margin: 3px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 6px;
}

.activity-timeline__by {
	color: var(--text-muted);
	font-weight: 400;
}

.activity-timeline__role {
	color: var(--text-muted);
	font-size: var(--text-xs);
}

.activity-timeline__when {
	color: var(--text-muted);
	font-size: var(--text-xs);
	margin-left: auto;
}

.activity-timeline__changes {
	list-style: none;
	margin: 6px 0 0;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 4px;
	font-size: var(--text-sm);
	color: var(--text-color);
	background: var(--subtle-fg, var(--control-bg));
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 8px 10px;
}

.activity-timeline__remarks {
	margin: 6px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: pre-wrap;
	background: var(--fg-color);
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 8px 10px;
}

.activity-composer {
	display: flex;
	flex-direction: column;
	gap: 8px;
	align-items: flex-end;
	margin-left: 36px;
}

.activity-composer textarea {
	width: 100%;
	resize: vertical;
}

.activity-sidebar {
	display: flex;
	flex-direction: column;
	gap: 16px;
}

.activity-sidebar__card {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 14px;
}

.activity-sidebar__meta {
	grid-template-columns: 1fr;
	gap: 8px 0;
}

.activity-detail__section-title {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
	margin-bottom: 10px;
}

.activity-detail__head-row {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 10px;
}

.activity-detail__head-row .activity-detail__section-title {
	margin-bottom: 0;
}

.activity-detail__meta {
	display: grid;
	gap: 10px 16px;
	margin: 0;
}

.activity-detail__meta dt {
	font-size: var(--text-xs);
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
}

.activity-detail__meta dd {
	margin: 2px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
}

.activity-detail__derived-note {
	font-size: var(--text-xs);
	color: var(--text-muted);
	font-style: italic;
	margin: 8px 0 0;
}

.activity-detail__dep-group {
	margin-bottom: 14px;
}

.activity-detail__dep-group:last-child {
	margin-bottom: 0;
}

.activity-detail__dep-label {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
	margin-bottom: 6px;
}

.activity-detail__dep-type {
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.activity-detail__list {
	list-style: none;
	margin: 0;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.activity-detail__list li {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 10px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 8px 12px;
}

.activity-detail__link {
	color: var(--text-color);
	font-weight: 500;
}

.activity-detail__milestone-dot {
	display: inline-block;
	width: 8px;
	height: 8px;
	margin-left: 6px;
	transform: rotate(45deg);
	background: var(--blue-500, var(--text-color));
	vertical-align: middle;
}

.activity-links__meta {
	display: flex;
	align-items: center;
	gap: 8px;
	flex: 0 0 auto;
}

.hub-link {
	color: var(--text-color);
	cursor: pointer;
	text-decoration: none;
	border-bottom: 1px dashed var(--border-color);
}

.hub-link:hover {
	color: var(--text-color);
	border-bottom-color: var(--text-color);
}

.hub-percent {
	display: flex;
	align-items: center;
	gap: 8px;
	min-width: 110px;
}

.hub-percent__track {
	flex: 1;
	height: 6px;
	border-radius: var(--border-radius-full);
	background: var(--control-bg);
	overflow: hidden;
}

.hub-percent__fill {
	height: 100%;
	background: var(--dark-green-500, var(--green-500));
}

.hub-percent__value {
	font-size: var(--text-xs);
	color: var(--text-muted);
	width: 32px;
	text-align: right;
}
</style>
