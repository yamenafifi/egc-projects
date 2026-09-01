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
import { add_stakeholder, remove_stakeholder, get_person_info } from "./project_profile_api";
import { useHubResource } from "../composables/useHubResource";
import { useRowSelection } from "../composables/useRowSelection";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import BulkActionsBar from "./BulkActionsBar.vue";

const props = defineProps({
	project: { type: String, required: true },
	context: { type: Object, default: null },
});

const { data, loading, error, reload } = useHubResource(() => get_directory(props.project));
watch(() => props.project, reload, { immediate: true });

const WRITE_ROLES = ["EGC Project Manager", "EGC Project Engineer", "EGC Document Controller", "System Manager"];
const can_write = computed(() => (frappe.user_roles || []).some((role) => WRITE_ROLES.includes(role)));

const scope_filter = ref("all");
const search = ref("");

const filtered = computed(() => {
	const term = search.value.trim().toLowerCase();
	return (data.value || []).filter((row) => {
		if (scope_filter.value === "internal" && !row.is_egc_internal) return false;
		if (scope_filter.value === "external" && row.is_egc_internal) return false;
		if (term) {
			const haystack = `${row.party_name} ${row.organization_name || ""} ${row.role}`.toLowerCase();
			if (!haystack.includes(term)) return false;
		}
		return true;
	});
});

//: Directory is browsed organization-first — group the already-filtered/searched list by
// resolved organization name (Customer/Supplier's real name, or an ad-hoc "Other" label — see
// api/directory.py's own organization_name resolution), preserving each group's original row
// order. People with no organization at all get one shared "No Organization" bucket, always
// last so a project's real organizations read first.
const NO_ORGANIZATION = "__no_organization__";
const grouped = computed(() => {
	const groups = new Map();
	for (const row of filtered.value) {
		const key = row.organization_name || NO_ORGANIZATION;
		if (!groups.has(key)) groups.set(key, []);
		groups.get(key).push(row);
	}
	const entries = [...groups.entries()].sort((a, b) => {
		if (a[0] === NO_ORGANIZATION) return 1;
		if (b[0] === NO_ORGANIZATION) return -1;
		return a[0].localeCompare(b[0]);
	});
	return entries.map(([name, rows]) => ({
		name: name === NO_ORGANIZATION ? __("No Organization") : name,
		rows,
	}));
});

const { selected, selected_count, all_selected, some_selected, is_selected, toggle, toggle_all, clear } =
	useRowSelection(filtered);

// Collapsed organizations, by group name — collapsing is purely a display toggle; selection
// state is independent, so a person selected inside a collapsed group stays selected.
const collapsed_groups = ref(new Set());
function toggle_group(name) {
	const next = new Set(collapsed_groups.value);
	if (next.has(name)) next.delete(name);
	else next.add(name);
	collapsed_groups.value = next;
}

function confirm_remove_selected() {
	const rows = filtered.value.filter((row) => selected.value.has(row.name));
	frappe.confirm(
		__("Remove {0} selected {1} from the Directory?", [rows.length, rows.length === 1 ? __("person") : __("people")]),
		async () => {
			const results = await Promise.allSettled(rows.map((row) => remove_stakeholder(props.project, row.name)));
			const failures = results.filter((r) => r.status === "rejected");
			clear();
			reload();
			if (!failures.length) {
				frappe.show_alert({ message: __("{0} removed.", [rows.length]), indicator: "green" });
			} else {
				frappe.msgprint({
					title: __("Some Removals Failed"),
					message: __("{0} removed, {1} failed.", [rows.length - failures.length, failures.length]),
					indicator: "orange",
				});
			}
		}
	);
}

function report_error(title, e) {
	frappe.msgprint({ title, message: e.message, indicator: "red" });
}

function open_record(row) {
	if (row.person) frappe.set_route("Form", "User", row.person);
}

// -- add to directory (same "pick a User or type a one-off party" pattern already used
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
				options: "User",
				description: __("Pick a Project Directory entry to auto-fill the fields below, or leave blank for a one-off party."),
				get_query: () => ({
					filters: { name: ["not in", (data.value || []).filter((r) => r.person).map((r) => r.person)] },
				}),
				onchange: async function () {
					const person = this.value;
					if (!person) return;
					const info = await get_person_info(person).catch(() => null);
					if (!info) return;
					dialog.set_value("party_name", info.party_name || "");
					dialog.set_value("organization_type", info.organization_type || "Customer");
					dialog.set_value("organization", info.organization || "");
					dialog.set_value("email", info.email || "");
					dialog.set_value("phone", info.phone || "");
				},
			},
			{ fieldname: "party_name", fieldtype: "Data", label: __("Party Name") },
			{
				fieldname: "organization_type",
				fieldtype: "Select",
				label: __("Organization Type"),
				options: ["Customer", "Supplier", "Other"],
				default: "Customer",
				onchange: function () {
					dialog.set_value("organization", "");
					dialog.set_value("organization_label", "");
				},
			},
			{
				fieldname: "organization",
				fieldtype: "Dynamic Link",
				label: __("Organization"),
				options: "organization_type",
				depends_on: 'eval:doc.organization_type != "Other"',
			},
			{
				fieldname: "organization_label",
				fieldtype: "Autocomplete",
				label: __("Organization"),
				// Suggests every ad-hoc organization name already used in this project's Directory.
				// ControlAutocomplete's own validate() silently blanks anything not already in
				// `options` — ignore_validation is required or a genuinely new name (e.g. "test")
				// would be dropped on submit instead of being accepted as free text.
				ignore_validation: 1,
				options: [
					...new Set(
						(data.value || [])
							.filter((r) => r.organization_type === "Other" && r.organization_label)
							.map((r) => r.organization_label)
					),
				],
				depends_on: 'eval:doc.organization_type == "Other"',
				description: __("A one-off organization name — not a Customer/Supplier record."),
			},
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

// Grant Access does exactly one thing: gives this person visibility into the project. It never
// asks which permission Role to apply — that's derived automatically from the row's own
// Stakeholder Role template (EGC Stakeholder Role.default_roles, applied server-side). When the
// row already has a login, there's nothing left to ask, so this is a plain confirm; a login-less
// row still needs an email to create one.
function open_grant_access_dialog(row) {
	if (row.person) {
		frappe.confirm(
			__("Grant {0} access to this project?", [row.party_name]),
			() => {
				grant_portal_access(props.project, row.name)
					.then(reload)
					.catch((e) => report_error(__("Could Not Grant Access"), e));
			}
		);
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
			grant_portal_access(props.project, row.name, values.email)
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
		revoke_portal_access(props.project, row.person)
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

			<BulkActionsBar
				v-if="selected_count"
				:selected-count="selected_count"
				:can-delete="can_write"
				:show-export="false"
				:delete-label="__('Remove Selected')"
				@delete="confirm_remove_selected"
				@clear="clear"
			/>

			<EmptyState v-if="!filtered.length" :title="__('No one matches these filters')" />
			<div v-else class="hub-table-wrap">
				<table class="hub-table">
					<thead>
						<tr>
							<th class="hub-table__check-col">
								<input
									type="checkbox"
									:checked="all_selected"
									:ref="(el) => el && (el.indeterminate = some_selected)"
									:title="__('Select all')"
									@click.stop="toggle_all"
								/>
							</th>
							<th>{{ __("Name") }}</th>
							<th>{{ __("Role") }}</th>
							<th>{{ __("Contact") }}</th>
							<th>{{ __("Portal Access") }}</th>
							<th v-if="can_write"></th>
						</tr>
					</thead>
					<template v-for="group in grouped" :key="group.name">
						<tbody class="hub-directory__group">
							<tr class="hub-directory__group-header" @click="toggle_group(group.name)">
								<td :colspan="can_write ? 6 : 5">
									<span
										class="hub-directory__group-toggle"
										:class="{ 'hub-directory__group-toggle--collapsed': collapsed_groups.has(group.name) }"
									>▾</span>
									{{ group.name }}
									<span class="hub-directory__group-count">{{ __("{0} people", [group.rows.length]) }}</span>
								</td>
							</tr>
						</tbody>
						<tbody v-if="!collapsed_groups.has(group.name)">
						<tr v-for="row in group.rows" :key="row.name" :class="{ 'hub-table__row--clickable': row.person }" @click="open_record(row)">
							<td class="hub-table__check-col" @click.stop>
								<input type="checkbox" :checked="is_selected(row)" @change="toggle(row)" />
							</td>
							<td>
								{{ row.party_name }}
								<span v-if="row.is_primary" class="indicator-pill blue">{{ __("Primary") }}</span>
							</td>
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
								<span v-if="row.is_admin_bypass" class="indicator-pill blue" :title="row.portal_roles.join(', ')">
									{{ __("Admin — sees all projects") }}
								</span>
								<span v-else-if="row.has_portal_access" class="indicator-pill green" :title="row.portal_roles.join(', ')">
									{{ __("Access granted") }}
								</span>
								<span v-else class="hub-directory__no-access">{{ __("No login") }}</span>
							</td>
							<td v-if="can_write" class="hub-directory__actions">
								<button type="button" class="btn btn-xs btn-default" @click.stop="open_change_role_dialog(row)">
									{{ __("Change Role") }}
								</button>
								<button
									v-if="row.has_portal_access && !row.is_admin_bypass"
									type="button"
									class="btn btn-xs btn-default"
									@click.stop="confirm_revoke_access(row)"
								>
									{{ __("Revoke Access") }}
								</button>
								<button v-else-if="!row.has_portal_access" type="button" class="btn btn-xs btn-default" @click.stop="open_grant_access_dialog(row)">
									{{ __("Grant Access") }}
								</button>
								<button type="button" class="btn btn-xs btn-default" @click.stop="confirm_remove(row)">
									{{ __("Remove") }}
								</button>
							</td>
						</tr>
						</tbody>
					</template>
				</table>
			</div>
		</template>
	</div>
</template>

<style scoped>
.hub-directory__group-header {
	cursor: pointer;
}

.hub-directory__group-header td {
	background: var(--control-bg);
	font-weight: 600;
	font-size: var(--text-sm);
	color: var(--text-color);
	padding: 6px 14px;
}

.hub-directory__group-header:hover td {
	background: var(--fg-hover-color, var(--control-bg));
}

.hub-directory__group-toggle {
	display: inline-block;
	width: 14px;
	color: var(--text-muted);
	transition: transform 0.1s ease;
}

.hub-directory__group-toggle--collapsed {
	transform: rotate(-90deg);
}

.hub-directory__group-count {
	margin-left: 8px;
	font-weight: 400;
	font-size: var(--text-xs);
	color: var(--text-muted);
}

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
