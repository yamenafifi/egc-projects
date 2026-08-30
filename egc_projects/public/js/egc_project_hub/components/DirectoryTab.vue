<!-- Directory — every person/organization on this project (EGC Project Stakeholder rows,
     api/directory.py), who's internal EGC staff vs. an external party, and whether they can log
     into the Hub at all (Portal Access: an EGC role + a User Permission scoping them to this one
     Project — the same pattern test_external_viewer.py already proves out, just reachable from
     here now instead of a System Manager wiring it up by hand from the Desk).

     Recording a response on an assigned Submittal step is authorized by identity, not by
     doctype role (see api/directory.py's own module docstring) — so an external party granted
     "External Viewer" here can already both watch this project's progress/timeline/submittals
     AND respond to any Submittal step assigned to them. No separate "reviewer" tier exists. -->
<script setup>
import { computed, ref, watch } from "vue";
import { get_directory, grant_portal_access, revoke_portal_access, update_stakeholder_role } from "./directory_api";
import { add_stakeholder, remove_stakeholder } from "./project_profile_api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { data, loading, error, reload } = useHubResource(() => get_directory(props.project));
watch(() => props.project, reload, { immediate: true });

const WRITE_ROLES = ["EGC Project Manager", "EGC Project Engineer", "EGC Document Controller", "System Manager"];
const can_write = computed(() => (frappe.user_roles || []).some((role) => WRITE_ROLES.includes(role)));

const GRANTABLE_ROLES = [
	{ value: "EGC Project Manager", label: __("Project Manager — internal, full access") },
	{ value: "EGC Project Engineer", label: __("Project Engineer — internal, engineering access") },
	{ value: "EGC Document Controller", label: __("Document Controller — internal, document control access") },
	{ value: "EGC Project Viewer", label: __("Project Viewer — internal, read-only") },
	{
		value: "EGC External Viewer",
		label: __("External Viewer — external, read-only + can respond to assigned Submittal steps"),
	},
];

const scope_filter = ref("all");
const search = ref("");

const filtered = computed(() => {
	const term = search.value.trim().toLowerCase();
	return (data.value || []).filter((row) => {
		if (scope_filter.value === "internal" && !row.is_egc_internal) return false;
		if (scope_filter.value === "external" && row.is_egc_internal) return false;
		if (term) {
			const haystack = `${row.party_name} ${row.organization || ""} ${row.role}`.toLowerCase();
			if (!haystack.includes(term)) return false;
		}
		return true;
	});
});

function report_error(title, e) {
	frappe.msgprint({ title, message: e.message, indicator: "red" });
}

function open_record(row) {
	if (row.person) frappe.set_route("Form", "Contact", row.person);
}

// -- add to directory (same "pick a Contact or type a one-off party" pattern already used
// by SubmittalsTab.vue/ProjectInfoTab.vue's own Add Stakeholder dialogs) -----------------------

function open_add_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add to Directory"),
		fields: [
			{ fieldname: "role", fieldtype: "Link", label: __("Role"), options: "EGC Stakeholder Role", reqd: 1 },
			{
				fieldname: "person",
				fieldtype: "Link",
				label: __("Person"),
				options: "Contact",
				description: __("Pick a Project Directory entry to auto-fill the fields below, or leave blank for a one-off party."),
			},
			{ fieldname: "party_name", fieldtype: "Data", label: __("Party Name") },
			{ fieldname: "organization", fieldtype: "Link", label: __("Organization"), options: "Customer" },
			{ fieldname: "email", fieldtype: "Data", label: __("Email") },
			{ fieldname: "phone", fieldtype: "Data", label: __("Phone") },
			{ fieldname: "is_primary", fieldtype: "Check", label: __("Primary") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			add_stakeholder(props.project, values)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => report_error(__("Could Not Add to Directory"), e));
		},
	});
	dialog.show();
}

function confirm_remove(row) {
	frappe.confirm(__("Remove {0} from the Directory?", [row.party_name]), () => {
		remove_stakeholder(props.project, row.name)
			.then(reload)
			.catch((e) => report_error(__("Could Not Remove"), e));
	});
}

// -- role -------------------------------------------------------------------------------------

function open_change_role_dialog(row) {
	const dialog = new frappe.ui.Dialog({
		title: __("Change Role"),
		fields: [
			{
				fieldname: "role",
				fieldtype: "Link",
				label: __("Role"),
				options: "EGC Stakeholder Role",
				default: row.role,
				reqd: 1,
			},
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			update_stakeholder_role(props.project, row.name, values.role)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => report_error(__("Could Not Change Role"), e));
		},
	});
	dialog.show();
}

// -- portal access -----------------------------------------------------------------------------

function open_grant_access_dialog(row) {
	const fields = [
		{
			fieldname: "role",
			fieldtype: "Select",
			label: __("Grant Role"),
			options: GRANTABLE_ROLES.map((r) => r.value),
			default: row.is_egc_internal ? "EGC Project Engineer" : "EGC External Viewer",
			reqd: 1,
			description: GRANTABLE_ROLES.map((r) => `${r.value}: ${r.label}`).join(" · "),
		},
	];
	if (!row.user) {
		fields.push({
			fieldname: "email",
			fieldtype: "Data",
			label: __("Email"),
			options: "Email",
			default: row.email,
			reqd: 1,
			description: __("A login is created for this address if one doesn't already exist."),
		});
	}
	const dialog = new frappe.ui.Dialog({
		title: __("Grant Portal Access — {0}", [row.party_name]),
		fields,
		primary_action_label: __("Grant Access"),
		primary_action(values) {
			grant_portal_access(props.project, row.name, values.role, values.email)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => report_error(__("Could Not Grant Access"), e));
		},
	});
	dialog.show();
}

function confirm_revoke_access(row) {
	frappe.confirm(__("Revoke {0}'s access to this project? Their login itself is not affected.", [row.party_name]), () => {
		revoke_portal_access(props.project, row.user)
			.then(reload)
			.catch((e) => report_error(__("Could Not Revoke Access"), e));
	});
}
</script>

<template>
	<div class="hub-directory">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />
		<EmptyState
			v-else-if="!(data || []).length"
			:title="__('No one in the Directory yet')"
			:description="__('Add the people and organizations on this project — internal EGC staff and external parties alike.')"
			:action-label="can_write ? __('+ Add to Directory') : ''"
			@action="open_add_dialog"
		/>

		<template v-else>
			<div class="hub-toolbar">
				<div class="hub-view-switch">
					<button
						v-for="opt in [{ key: 'all', label: __('All') }, { key: 'internal', label: __('Internal') }, { key: 'external', label: __('External') }]"
						:key="opt.key"
						type="button"
						class="hub-view-switch__btn"
						:class="{ 'hub-view-switch__btn--active': scope_filter === opt.key }"
						@click="scope_filter = opt.key"
					>
						{{ opt.label }}
					</button>
				</div>
				<input v-model="search" type="text" :placeholder="__('Search name, organization, role…')" />
				<div class="hub-toolbar__spacer" />
				<button v-if="can_write" type="button" class="btn btn-sm btn-primary" @click="open_add_dialog">
					{{ __("+ Add to Directory") }}
				</button>
			</div>

			<EmptyState v-if="!filtered.length" :title="__('No one matches these filters')" />
			<div v-else class="hub-table-wrap">
				<table class="hub-table">
					<thead>
						<tr>
							<th>{{ __("Name") }}</th>
							<th>{{ __("Organization") }}</th>
							<th>{{ __("Role") }}</th>
							<th>{{ __("Contact") }}</th>
							<th>{{ __("Portal Access") }}</th>
							<th v-if="can_write"></th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in filtered" :key="row.name" :class="{ 'hub-table__row--clickable': row.person }" @click="open_record(row)">
							<td>
								{{ row.party_name }}
								<span v-if="row.is_primary" class="indicator-pill blue">{{ __("Primary") }}</span>
							</td>
							<td>{{ row.organization || "—" }}</td>
							<td>
								{{ row.role }}
								<span class="hub-directory__scope-tag" :class="{ 'hub-directory__scope-tag--internal': row.is_egc_internal }">
									{{ row.is_egc_internal ? __("Internal") : __("External") }}
								</span>
							</td>
							<td class="hub-table__truncate" :title="[row.email, row.phone].filter(Boolean).join(' · ')">
								{{ [row.email, row.phone].filter(Boolean).join(" · ") || "—" }}
							</td>
							<td>
								<span v-if="row.has_portal_access" class="indicator-pill green" :title="row.portal_roles.join(', ')">
									{{ __("Access granted") }}
								</span>
								<span v-else class="hub-directory__no-access">{{ __("No login") }}</span>
							</td>
							<td v-if="can_write" class="hub-directory__actions">
								<button type="button" class="btn btn-xs btn-default" @click.stop="open_change_role_dialog(row)">
									{{ __("Change Role") }}
								</button>
								<button
									v-if="row.has_portal_access"
									type="button"
									class="btn btn-xs btn-default"
									@click.stop="confirm_revoke_access(row)"
								>
									{{ __("Revoke Access") }}
								</button>
								<button v-else type="button" class="btn btn-xs btn-default" @click.stop="open_grant_access_dialog(row)">
									{{ __("Grant Access") }}
								</button>
								<button type="button" class="btn btn-xs btn-default" @click.stop="confirm_remove(row)">
									{{ __("Remove") }}
								</button>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
		</template>
	</div>
</template>

<style scoped>
.hub-view-switch {
	display: flex;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	overflow: hidden;
	flex: 0 0 auto;
}

.hub-view-switch__btn {
	appearance: none;
	border: none;
	background: var(--fg-color);
	color: var(--text-muted);
	padding: 5px 12px;
	font-size: var(--text-sm);
	cursor: pointer;
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

.hub-toolbar__spacer {
	flex: 1 1 auto;
}

.hub-directory__scope-tag {
	display: inline-block;
	margin-left: 6px;
	padding: 0 6px;
	font-size: var(--text-xs);
	font-weight: 500;
	color: var(--text-muted);
	background: var(--control-bg);
	border-radius: var(--border-radius-full);
	white-space: nowrap;
}

.hub-directory__scope-tag--internal {
	color: var(--blue-500, var(--text-color));
}

.hub-directory__no-access {
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.hub-directory__actions {
	display: flex;
	gap: 6px;
	white-space: nowrap;
}
</style>
