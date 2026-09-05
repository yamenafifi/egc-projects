<!-- Directory Person profile — a full-page view that REPLACES the Directory list, the same
     established pattern SubmittalDetail.vue/DocumentDetail.vue/ActivityFullPage.vue already use
     (see SubmittalDetail.vue's own header comment for the rationale — a standing product
     principle, not a one-off choice). Direct instruction: clicking a Directory row used to route
     to the raw native User form (nothing project-specific, not editable from here at all); this
     replaces that with a real profile — who they are on THIS project, what they've actually done
     here, and a proper edit surface for every field the row has, not just role.

     "What they've done" is drawn from this app's own real business objects, not a generic audit
     log: their own responded review steps (a reviewer's actual verdict history — the core action
     this whole app tracks), documents they originated, and what they're on the team for
     (EGC Assignment). All three only populate once the row has a real login (`person`) to
     correlate against — a login-less party still gets the full profile + edit, just no activity
     section yet. -->
<script setup>
import { ref, computed, watch } from "vue";
import { get_person_profile, grant_portal_access, revoke_portal_access } from "./directory_api";
import { update_stakeholder } from "./project_profile_api";
import { useHubResource } from "../composables/useHubResource";
import { useHubRoute } from "../composables/useHubRoute";
import { openSubmittalIntent } from "../composables/useOpenSubmittalIntent";
import { openDocumentIntent } from "../composables/useOpenDocumentIntent";
import { openActivityIntent } from "../composables/useOpenActivityIntent";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";

const props = defineProps({
	project: { type: String, required: true },
	rowName: { type: String, required: true },
	canWrite: { type: Boolean, default: false },
});
const emit = defineEmits(["close", "changed"]);

const { data, loading, error, reload } = useHubResource(() => get_person_profile(props.project, props.rowName));
watch(() => props.rowName, reload, { immediate: true });

const { setTab } = useHubRoute();

function open_submittal(name) {
	openSubmittalIntent.submittal = name;
	setTab("submittals");
}
function open_document(name) {
	openDocumentIntent.document = name;
	setTab("documents");
}
function open_activity(name) {
	openActivityIntent.activity = name;
	setTab("activities");
}

const PARENT_DOCTYPE_LABEL = {
	"EGC Submittal": __("Submittal"),
	"EGC Project Document": __("Document"),
	"EGC Activity": __("Activity"),
};
function open_assignment_parent(row) {
	if (row.parent_doctype === "EGC Submittal") open_submittal(row.parent_name);
	else if (row.parent_doctype === "EGC Project Document") open_document(row.parent_name);
	else if (row.parent_doctype === "EGC Activity") open_activity(row.parent_name);
}

const RESPONSE_TONE = {
	Approved: "green",
	"Approved with Comments": "green",
	Rejected: "red",
	"Revise & Resubmit": "orange",
};
function response_tone(response) {
	return RESPONSE_TONE[response] || "grey";
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}
function format_datetime(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

function report_error(title, e) {
	frappe.msgprint({ title, message: e.message, indicator: "red" });
}

function notify_changed() {
	emit("changed");
	reload();
}

// -- edit: a fuller dialog than the list's own narrow "Change Role" — every field this row has
// except `person` (see project_profile.py's own STAKEHOLDER_EDITABLE_FIELDS docstring for why
// that one specifically stays out). Pre-filled from the row's current values, not blank. --------

function open_edit_dialog() {
	const row = data.value.row;
	// Party Name/Organization/Email/Phone are only genuinely this row's own data for a one-off
	// party with no login (`person` blank) — the moment a login IS linked,
	// EGCProjectStakeholder.fetch_from_person() (validate(), egc_project_stakeholder.py)
	// unconditionally re-derives all four from that User on every save, "so this row's own
	// display fields always mirror the Directory record rather than drifting into an independent
	// copy" (that doctype's own docstring). Confirmed directly, not assumed: an earlier version of
	// this dialog let you edit them for a person-linked row and the edit was silently discarded.
	// Shown read-only here instead of just omitted, so it's still clear where those values come
	// from — editing role/is_primary is what this dialog is actually for in that case.
	const locked = !!row.person;
	const dialog = new frappe.ui.Dialog({
		title: __("Edit {0}", [row.party_name]),
		fields: [
			{
				fieldname: "party_name",
				fieldtype: "Data",
				label: __("Party Name"),
				default: row.party_name,
				reqd: 1,
				read_only: locked,
				description: locked ? __("Synced from {0}'s own login — edit their User record to change this.", [row.party_name]) : "",
			},
			{ fieldname: "role", fieldtype: "Link", label: __("Role"), options: "EGC Stakeholder Role", default: row.role, reqd: 1 },
			{
				fieldname: "organization_type",
				fieldtype: "Select",
				label: __("Organization Type"),
				options: ["Customer", "Supplier", "Other"],
				default: row.organization_type || "Customer",
				read_only: locked,
				onchange: function () {
					if (locked) return;
					dialog.set_value("organization", "");
					dialog.set_value("organization_label", "");
				},
			},
			{
				fieldname: "organization",
				fieldtype: "Dynamic Link",
				label: __("Organization"),
				options: "organization_type",
				default: row.organization_type !== "Other" ? row.organization : "",
				depends_on: 'eval:doc.organization_type != "Other"',
				read_only: locked,
			},
			{
				fieldname: "organization_label",
				fieldtype: "Data",
				label: __("Organization"),
				default: row.organization_type === "Other" ? row.organization_label : "",
				depends_on: 'eval:doc.organization_type == "Other"',
				description: locked ? "" : __("A one-off organization name — not a Customer/Supplier record."),
				read_only: locked,
			},
			{ fieldname: "email", fieldtype: "Data", label: __("Email"), default: row.email, read_only: locked },
			{ fieldname: "phone", fieldtype: "Data", label: __("Phone"), default: row.phone, read_only: locked },
			{ fieldname: "is_primary", fieldtype: "Check", label: __("Primary"), default: row.is_primary },
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			update_stakeholder(props.project, props.rowName, values)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => report_error(__("Could Not Save"), e));
		},
	});
	dialog.show();
}

function open_grant_access_dialog() {
	const row = data.value.row;
	if (row.person) {
		frappe.confirm(__("Grant {0} access to this project?", [row.party_name]), () => {
			grant_portal_access(props.project, props.rowName).then(notify_changed).catch((e) => report_error(__("Could Not Grant Access"), e));
		});
		return;
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Grant Portal Access — {0}", [row.party_name]),
		fields: [
			{
				fieldname: "email",
				fieldtype: "Data",
				label: __("Email"),
				options: "Email",
				default: row.email,
				reqd: 1,
				description: __("A login is created for this address since none exists yet."),
			},
		],
		primary_action_label: __("Grant Access"),
		primary_action(values) {
			grant_portal_access(props.project, props.rowName, values.email)
				.then(() => {
					dialog.hide();
					notify_changed();
				})
				.catch((e) => report_error(__("Could Not Grant Access"), e));
		},
	});
	dialog.show();
}

function confirm_revoke_access() {
	const row = data.value.row;
	frappe.confirm(__("Revoke {0}'s access to this project? Their login itself is not affected.", [row.party_name]), () => {
		revoke_portal_access(props.project, row.person).then(notify_changed).catch((e) => report_error(__("Could Not Revoke Access"), e));
	});
}

const initials = computed(() => {
	const name = data.value?.row?.party_name || "";
	return name
		.split(/\s+/)
		.filter(Boolean)
		.slice(0, 2)
		.map((w) => w[0].toUpperCase())
		.join("");
});
</script>

<template>
	<div class="person-page">
		<LoadingState v-if="loading" :rows="6" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />

		<template v-else-if="data">
			<div class="person-page__topbar">
				<a href="#" class="hub-link person-page__back" @click.prevent="$emit('close')">
					{{ __("← Back to Directory") }}
				</a>
				<a v-if="canWrite" href="#" class="hub-link" @click.prevent="open_edit_dialog">{{ __("Edit") }}</a>
			</div>

			<div class="person-page__identity">
				<div class="person-page__avatar">{{ initials || "?" }}</div>
				<div class="person-page__identity-main">
					<h1 class="person-page__title">
						{{ data.row.party_name }}
						<span v-if="data.row.is_primary" class="indicator-pill blue">{{ __("Primary") }}</span>
					</h1>
					<div class="person-page__meta-row">
						<span class="person-page__scope-tag" :class="{ 'person-page__scope-tag--internal': data.row.is_egc_internal }">
							{{ data.row.is_egc_internal ? __("Internal") : __("External") }}
						</span>
						<span>{{ data.row.role }}</span>
						<span v-if="data.row.organization_name">· {{ data.row.organization_name }}</span>
					</div>
					<div class="person-page__meta-row person-page__meta-row--muted">
						{{ [data.row.email, data.row.phone].filter(Boolean).join(" · ") || __("No contact info on file") }}
					</div>
					<div class="person-page__access-row">
						<span v-if="data.row.is_admin_bypass" class="indicator-pill blue">{{ __("Admin — sees all projects") }}</span>
						<span v-else-if="data.row.is_internal_unscoped" class="indicator-pill blue">{{ __("Internal — sees all projects") }}</span>
						<span v-else-if="data.row.has_portal_access" class="indicator-pill green">{{ __("Access granted") }}</span>
						<span v-else class="person-page__no-access">{{ __("No login") }}</span>
						<button
							v-if="canWrite && data.row.has_portal_access && !data.row.is_admin_bypass && !data.row.is_internal_unscoped"
							type="button"
							class="btn btn-xs btn-default"
							@click="confirm_revoke_access"
						>
							{{ __("Revoke Access") }}
						</button>
						<button v-else-if="canWrite && !data.row.has_portal_access" type="button" class="btn btn-xs btn-default" @click="open_grant_access_dialog">
							{{ __("Grant Access") }}
						</button>
					</div>
				</div>
			</div>

			<div v-if="!data.row.person" class="person-page__no-login-note">
				{{ __("This person has no login yet, so there's no project activity to show — grant access above once they need to sign in.") }}
			</div>

			<template v-else>
				<section class="hub-card person-page__section">
					<h3 class="hub-card__title">{{ __("Review Responses") }}</h3>
					<p v-if="!data.activity.reviews.length" class="person-page__empty">{{ __("No review responses recorded yet.") }}</p>
					<table v-else class="hub-table">
						<thead>
							<tr>
								<th>{{ __("Submittal") }}</th>
								<th>{{ __("Stage") }}</th>
								<th>{{ __("Response") }}</th>
								<th>{{ __("Date") }}</th>
								<th>{{ __("Remarks") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in data.activity.reviews" :key="row.name">
								<td>
									<a v-if="row.submittal" href="#" class="hub-link" @click.prevent="open_submittal(row.submittal)">
										{{ row.submittal_number || row.submittal }}
									</a>
									<span v-else>—</span>
									<div v-if="row.submittal_title" class="person-page__row-subtitle">{{ row.submittal_title }}</div>
								</td>
								<td>{{ row.sequence }}</td>
								<td><span class="indicator-pill" :class="response_tone(row.response)">{{ row.response }}</span></td>
								<td>{{ format_date(row.response_date) }}</td>
								<td class="hub-table__truncate" :title="row.response_remarks">{{ row.response_remarks || "—" }}</td>
							</tr>
						</tbody>
					</table>
				</section>

				<section class="hub-card person-page__section">
					<h3 class="hub-card__title">{{ __("Documents Originated") }}</h3>
					<p v-if="!data.activity.documents.length" class="person-page__empty">{{ __("Hasn't originated any documents on this project.") }}</p>
					<table v-else class="hub-table">
						<thead>
							<tr>
								<th>{{ __("Document") }}</th>
								<th>{{ __("Status") }}</th>
								<th>{{ __("Approval") }}</th>
								<th>{{ __("Created") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in data.activity.documents" :key="row.name">
								<td>
									<a href="#" class="hub-link" @click.prevent="open_document(row.name)">{{ row.document_number }}</a>
									<div class="person-page__row-subtitle">{{ row.title }}</div>
								</td>
								<td>{{ row.document_status }}</td>
								<td>{{ row.approval_status }}</td>
								<td>{{ format_datetime(row.creation) }}</td>
							</tr>
						</tbody>
					</table>
				</section>

				<section class="hub-card person-page__section">
					<h3 class="hub-card__title">{{ __("Team") }}</h3>
					<p v-if="!data.activity.assignments.length" class="person-page__empty">{{ __("Not on the team for any record on this project yet.") }}</p>
					<table v-else class="hub-table">
						<thead>
							<tr>
								<th>{{ __("Record") }}</th>
								<th>{{ __("Type") }}</th>
								<th>{{ __("Role") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in data.activity.assignments" :key="row.name">
								<td>
									<a href="#" class="hub-link" @click.prevent="open_assignment_parent(row)">
										{{ row.parent_title || row.parent_name }}
									</a>
								</td>
								<td>{{ PARENT_DOCTYPE_LABEL[row.parent_doctype] || row.parent_doctype }}</td>
								<td>
									{{ row.assignment_role }}
									<span v-if="row.is_primary" class="indicator-pill blue">{{ __("Primary") }}</span>
								</td>
							</tr>
						</tbody>
					</table>
				</section>
			</template>
		</template>
	</div>
</template>

<style scoped>
.hub-link {
	color: var(--text-color);
	cursor: pointer;
	text-decoration: none;
	border-bottom: 1px dashed var(--border-color);
}

.hub-link:hover {
	color: var(--text-muted);
}

.person-page {
	display: flex;
	flex-direction: column;
	gap: 18px;
}

.person-page__topbar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
}

.person-page__back {
	font-weight: 500;
}

.person-page__identity {
	display: flex;
	gap: 16px;
	border-bottom: 1px solid var(--border-color);
	padding-bottom: 16px;
}

.person-page__avatar {
	flex: 0 0 auto;
	width: 56px;
	height: 56px;
	border-radius: 50%;
	background: var(--control-bg);
	color: var(--text-color);
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: var(--text-lg, 18px);
	font-weight: 600;
}

.person-page__identity-main {
	flex: 1 1 auto;
	min-width: 0;
	display: flex;
	flex-direction: column;
	gap: 6px;
}

.person-page__title {
	font-size: var(--text-2xl, 22px);
	font-weight: 600;
	color: var(--text-color);
	margin: 0;
	display: flex;
	align-items: center;
	gap: 8px;
}

.person-page__meta-row {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 8px;
	font-size: var(--text-sm);
	color: var(--text-color);
}

.person-page__meta-row--muted {
	color: var(--text-muted);
	font-size: var(--text-xs);
}

.person-page__scope-tag {
	display: inline-block;
	padding: 0 6px;
	font-size: var(--text-xs);
	font-weight: 500;
	color: var(--text-muted);
	background: var(--control-bg);
	border-radius: var(--border-radius-full);
}

.person-page__scope-tag--internal {
	color: var(--blue-500, var(--text-color));
}

.person-page__access-row {
	display: flex;
	align-items: center;
	gap: 10px;
	margin-top: 4px;
}

.person-page__no-access {
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.person-page__no-login-note {
	font-size: var(--text-sm);
	color: var(--text-muted);
	background: var(--control-bg);
	border-radius: var(--border-radius);
	padding: 12px 14px;
}

.person-page__section {
	display: flex;
	flex-direction: column;
	gap: 4px;
}

.person-page__empty {
	font-size: var(--text-sm);
	color: var(--text-muted);
	margin: 0;
}

.person-page__row-subtitle {
	font-size: var(--text-xs);
	color: var(--text-muted);
	margin-top: 2px;
}
</style>
