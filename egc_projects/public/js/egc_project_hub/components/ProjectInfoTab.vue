<!-- Project Information — a curated, EDITABLE view of the `custom_egc_*` fields that live
     directly on the core `Project` doctype (project_custom_fields.py). Level 0 §8 reversed an
     earlier decision in this same app: routine Project setup used to be routed entirely to the
     native `Project` form ("Do not force routine Project setup through the raw ERPNext Project
     form" — the newer, governing instruction). The native form still works — nothing here makes
     it read-only — it's just no longer the primary path; "Open Project Form" stays as a secondary
     escape hatch for anything genuinely native-form-only. -->
<script setup>
import { computed, watch } from "vue";
import { get_project_info, get_project_context } from "../api";
import {
	save_project_profile,
	add_stakeholder,
	remove_stakeholder,
	add_equipment_item,
	remove_equipment_item,
} from "./project_profile_api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
	project: { type: String, required: true },
});

async function load() {
	const [info, context] = await Promise.all([
		get_project_info(props.project),
		get_project_context(props.project),
	]);
	return { info, currency: context.currency || "", can_edit: Boolean(context.permissions?.edit_profile) };
}

const { data, loading, error, reload } = useHubResource(load);
watch(() => props.project, reload, { immediate: true });

const has_any_data = computed(() => {
	const info = data.value?.info;
	if (!info) return false;
	const scalar_fields = [
		"project_code",
		"project_stage",
		"sector",
		"delivery_method",
		"contract_type",
		"project_description",
		"project_image",
		"project_address",
		"site_contact_name",
		"site_contact_phone",
		"site_contact_email",
		"contract_date",
		"forecast_completion_date",
		"warranty_start_date",
		"dlp_end_date",
	];
	return (
		scalar_fields.some((key) => info[key]) ||
		info.stakeholders.length > 0 ||
		info.equipment_items.length > 0
	);
});

// `project_address_display` is `render_address`'s own HTML-formatted string (built for print
// templates, `<br>`-joined) — converting to plain newlines lets the existing `white-space:
// pre-wrap` text style render it correctly without reaching for `v-html` over server-rendered
// HTML this component doesn't otherwise need to trust.
const project_address_lines = computed(() => {
	const display = data.value?.info?.project_address_display;
	if (!display) return "";
	return display
		.replace(/<br\s*\/?>/gi, "\n")
		.split("\n")
		.map((line) => line.trim())
		.filter(Boolean)
		.join("\n");
});

function open_native_form() {
	frappe.set_route("Form", "Project", props.project);
}

function open_address_form() {
	frappe.set_route("Form", "Address", data.value.info.project_address);
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

function stakeholder_party(row) {
	return row.party_name || row.organization || "—";
}

function report_error(title, e) {
	frappe.msgprint({ title, message: e.message, indicator: "red" });
}

// -- edit scalar fields (Classification/Description/Address/Site Contact/Contract Dates) --------

function open_edit_details_dialog() {
	const info = data.value.info;
	const dialog = new frappe.ui.Dialog({
		title: __("Edit Project Details"),
		size: "large",
		fields: [
			{ fieldtype: "Section Break", label: __("Classification") },
			{ fieldname: "project_code", fieldtype: "Data", label: __("Project Code"), default: info.project_code },
			{
				fieldname: "project_stage",
				fieldtype: "Select",
				label: __("Project Stage"),
				options: "\nDesign\nProcurement\nConstruction\nCommissioning\nCloseout\nWarranty",
				default: info.project_stage,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "sector",
				fieldtype: "Select",
				label: __("Sector"),
				options: "\nHealthcare\nIndustrial\nCommercial\nInfrastructure\nOther",
				default: info.sector,
			},
			{
				fieldname: "delivery_method",
				fieldtype: "Select",
				label: __("Delivery Method"),
				options: "\nDesign-Bid-Build\nDesign-Build\nEPC\nTurnkey\nOther",
				default: info.delivery_method,
			},
			{
				fieldname: "contract_type",
				fieldtype: "Select",
				label: __("Contract Type"),
				options: "\nLump Sum\nUnit Price\nCost Plus\nTime & Material\nOther",
				default: info.contract_type,
			},
			{ fieldtype: "Section Break", label: __("Description") },
			{
				fieldname: "project_description",
				fieldtype: "Small Text",
				label: __("Project Description"),
				default: info.project_description,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "project_image",
				fieldtype: "Attach Image",
				label: __("Project Image"),
				default: info.project_image,
				options: { doctype: "Project", docname: props.project, fieldname: "custom_egc_project_image" },
			},
			{ fieldtype: "Section Break", label: __("Address") },
			{
				fieldname: "project_address",
				fieldtype: "Link",
				label: __("Project Address"),
				options: "Address",
				default: info.project_address,
				get_query: () => ({
					query: "egc_projects.egc_projects.project_profile.get_addresses_for_project",
					filters: { project: props.project },
				}),
				// Same "born already linked" fix as project.js — without it, "Create a new
				// Address" here would save an Address the query above can never find again.
				get_route_options_for_new_doc: () => ({
					links: [{ link_doctype: "Project", link_name: props.project }],
				}),
			},
			{ fieldtype: "Section Break", label: __("Site Contact") },
			{
				fieldname: "site_contact_name",
				fieldtype: "Data",
				label: __("Site Contact Name"),
				default: info.site_contact_name,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "site_contact_phone",
				fieldtype: "Data",
				label: __("Site Contact Phone"),
				default: info.site_contact_phone,
			},
			{
				fieldname: "site_contact_email",
				fieldtype: "Data",
				label: __("Site Contact Email"),
				default: info.site_contact_email,
			},
			{ fieldtype: "Section Break", label: __("Contract Dates") },
			{ fieldname: "contract_date", fieldtype: "Date", label: __("Contract Date"), default: info.contract_date },
			{
				fieldname: "forecast_completion_date",
				fieldtype: "Date",
				label: __("Forecast Completion Date"),
				default: info.forecast_completion_date,
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "warranty_start_date",
				fieldtype: "Date",
				label: __("Warranty Start Date"),
				default: info.warranty_start_date,
			},
			{ fieldname: "dlp_end_date", fieldtype: "Date", label: __("DLP End Date"), default: info.dlp_end_date },
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			save_project_profile(props.project, values)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => report_error(__("Could Not Save Project Details"), e));
		},
	});
	dialog.show();
}

// -- stakeholders ---------------------------------------------------------------------------

function open_add_stakeholder_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Stakeholder"),
		fields: [
			{ fieldname: "role", fieldtype: "Link", label: __("Role"), options: "EGC Stakeholder Role", reqd: 1 },
			{
				fieldname: "person",
				fieldtype: "Link",
				label: __("Person"),
				options: "EGC Person",
				description: __("Pick a Project Directory entry to auto-fill the fields below, or leave blank for a one-off party."),
			},
			{ fieldname: "party_name", fieldtype: "Data", label: __("Party Name") },
			{ fieldname: "organization", fieldtype: "Link", label: __("Organization"), options: "EGC Organization" },
			{ fieldname: "user", fieldtype: "Link", label: __("User"), options: "User" },
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
				.catch((e) => report_error(__("Could Not Add Stakeholder"), e));
		},
	});
	dialog.show();
}

function confirm_remove_stakeholder(row) {
	frappe.confirm(__("Remove {0} as a stakeholder on this project?", [stakeholder_party(row)]), () => {
		remove_stakeholder(props.project, row.name)
			.then(reload)
			.catch((e) => report_error(__("Could Not Remove Stakeholder"), e));
	});
}

// -- healthcare / equipment items ------------------------------------------------------------

function open_add_equipment_dialog() {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Equipment Item"),
		fields: [
			{ fieldname: "facility", fieldtype: "Data", label: __("Facility") },
			{ fieldname: "department", fieldtype: "Data", label: __("Department") },
			{ fieldname: "modality", fieldtype: "Link", label: __("Modality"), options: "EGC Modality" },
			{
				fieldname: "wbs_node",
				fieldtype: "Link",
				label: __("WBS Node"),
				options: "EGC WBS Node",
				get_query: () => ({ filters: { project: props.project } }),
			},
			{
				fieldname: "equipment_manufacturer",
				fieldtype: "Link",
				label: __("Equipment Manufacturer"),
				options: "EGC Equipment Manufacturer",
			},
			{ fieldname: "equipment_model", fieldtype: "Data", label: __("Equipment Model") },
			{ fieldname: "oem_reference", fieldtype: "Data", label: __("OEM Reference") },
			{ fieldname: "equipment_delivery_target", fieldtype: "Date", label: __("Equipment Delivery Target") },
			{ fieldname: "room_ready_target", fieldtype: "Date", label: __("Room Ready Target") },
			{ fieldname: "oem_installation_target", fieldtype: "Date", label: __("OEM Installation Target") },
			{ fieldname: "commissioning_target", fieldtype: "Date", label: __("Commissioning Target") },
			{ fieldname: "notes", fieldtype: "Small Text", label: __("Notes") },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			add_equipment_item(props.project, values)
				.then(() => {
					dialog.hide();
					reload();
				})
				.catch((e) => report_error(__("Could Not Add Equipment Item"), e));
		},
	});
	dialog.show();
}

function confirm_remove_equipment(row) {
	frappe.confirm(__("Remove this equipment item?"), () => {
		remove_equipment_item(props.project, row.name)
			.then(reload)
			.catch((e) => report_error(__("Could Not Remove Equipment Item"), e));
	});
}
</script>

<template>
	<div class="hub-project-info">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />

		<template v-else-if="data">
			<div class="hub-project-info__toolbar">
				<button v-if="data.can_edit" type="button" class="btn btn-sm btn-primary" @click="open_edit_details_dialog">
					{{ __("Edit Details") }}
				</button>
				<a href="#" class="hub-link" @click.prevent="open_native_form">{{ __("Open Project Form") }}</a>
			</div>

			<EmptyState
				v-if="!has_any_data"
				:title="__('No project information yet')"
				:description="__('Classification, stakeholders, address and contract dates for this project — add them from here.')"
			/>

			<template v-else>
				<section class="hub-card hub-project-info__section">
					<div class="hub-card__title">{{ __("Classification") }}</div>
					<div v-if="data.info.project_image" class="hub-project-info__image-row">
						<img :src="data.info.project_image" class="hub-project-info__image" :alt="__('Project image')" />
					</div>
					<dl class="hub-info-grid">
						<div>
							<dt>{{ __("Project Code") }}</dt>
							<dd>{{ data.info.project_code || "—" }}</dd>
						</div>
						<div>
							<dt>{{ __("Project Stage") }}</dt>
							<dd>{{ data.info.project_stage || "—" }}</dd>
						</div>
						<div>
							<dt>{{ __("Sector") }}</dt>
							<dd>{{ data.info.sector || "—" }}</dd>
						</div>
						<div>
							<dt>{{ __("Delivery Method") }}</dt>
							<dd>{{ data.info.delivery_method || "—" }}</dd>
						</div>
						<div>
							<dt>{{ __("Contract Type") }}</dt>
							<dd>{{ data.info.contract_type || "—" }}</dd>
						</div>
					</dl>
					<p v-if="data.info.project_description" class="hub-project-info__text">
						{{ data.info.project_description }}
					</p>
				</section>

				<section class="hub-card hub-project-info__section">
					<div class="hub-project-info__section-head">
						<div class="hub-card__title">{{ __("Stakeholders") }}</div>
						<button v-if="data.can_edit" type="button" class="btn btn-xs btn-default" @click="open_add_stakeholder_dialog">
							{{ __("Add Stakeholder") }}
						</button>
					</div>
					<EmptyState v-if="!data.info.stakeholders.length" :title="__('No stakeholders yet')" />
					<ul v-else class="hub-project-info__list">
						<li v-for="row in data.info.stakeholders" :key="row.name">
							<span class="hub-project-info__list-role">{{ row.role }}</span>
							<span class="hub-project-info__list-name">{{ stakeholder_party(row) }}</span>
							<span v-if="row.is_primary" class="indicator-pill blue">{{ __("Primary") }}</span>
							<button
								v-if="data.can_edit"
								type="button"
								class="btn btn-xs btn-default"
								:title="__('Remove')"
								@click="confirm_remove_stakeholder(row)"
							>
								&times;
							</button>
						</li>
					</ul>
				</section>

				<section class="hub-card hub-project-info__section">
					<div class="hub-card__title">{{ __("Address") }}</div>
					<EmptyState v-if="!data.info.project_address" :title="__('No address set yet')" />
					<template v-else>
						<p class="hub-project-info__text">{{ project_address_lines }}</p>
						<a href="#" class="hub-link" @click.prevent="open_address_form">{{ __("Open Address record") }}</a>
					</template>
				</section>

				<section class="hub-card hub-project-info__section">
					<div class="hub-card__title">{{ __("Site Contact") }}</div>
					<dl class="hub-info-grid">
						<div>
							<dt>{{ __("Name") }}</dt>
							<dd>{{ data.info.site_contact_name || "—" }}</dd>
						</div>
						<div>
							<dt>{{ __("Phone") }}</dt>
							<dd>{{ data.info.site_contact_phone || "—" }}</dd>
						</div>
						<div>
							<dt>{{ __("Email") }}</dt>
							<dd>{{ data.info.site_contact_email || "—" }}</dd>
						</div>
					</dl>
				</section>

				<section class="hub-card hub-project-info__section">
					<div class="hub-card__title">{{ __("Contract Dates") }}</div>
					<dl class="hub-info-grid">
						<div>
							<dt>{{ __("Contract Date") }}</dt>
							<dd>{{ format_date(data.info.contract_date) }}</dd>
						</div>
						<div>
							<dt>{{ __("Forecast Completion") }}</dt>
							<dd>{{ format_date(data.info.forecast_completion_date) }}</dd>
						</div>
						<div>
							<dt>{{ __("Warranty Start") }}</dt>
							<dd>{{ format_date(data.info.warranty_start_date) }}</dd>
						</div>
						<div>
							<dt>{{ __("DLP End") }}</dt>
							<dd>{{ format_date(data.info.dlp_end_date) }}</dd>
						</div>
					</dl>
				</section>

				<section class="hub-card hub-project-info__section">
					<div class="hub-project-info__section-head">
						<div class="hub-card__title">{{ __("Healthcare / Equipment") }}</div>
						<button v-if="data.can_edit" type="button" class="btn btn-xs btn-default" @click="open_add_equipment_dialog">
							{{ __("Add Equipment") }}
						</button>
					</div>
					<EmptyState v-if="!data.info.equipment_items.length" :title="__('No equipment items yet')" />
					<div v-else class="hub-table-wrap">
						<table class="hub-table">
							<thead>
								<tr>
									<th>{{ __("Facility") }}</th>
									<th>{{ __("Modality") }}</th>
									<th>{{ __("Manufacturer") }}</th>
									<th>{{ __("Model") }}</th>
									<th>{{ __("Delivery Target") }}</th>
									<th>{{ __("Commissioning Target") }}</th>
									<th v-if="data.can_edit"></th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="row in data.info.equipment_items" :key="row.name">
									<td>{{ row.facility || "—" }}</td>
									<td>{{ row.modality || "—" }}</td>
									<td>{{ row.equipment_manufacturer || "—" }}</td>
									<td>{{ row.equipment_model || "—" }}</td>
									<td>{{ format_date(row.equipment_delivery_target) }}</td>
									<td>{{ format_date(row.commissioning_target) }}</td>
									<td v-if="data.can_edit">
										<button
											type="button"
											class="btn btn-xs btn-default"
											:title="__('Remove')"
											@click="confirm_remove_equipment(row)"
										>
											&times;
										</button>
									</td>
								</tr>
							</tbody>
						</table>
					</div>
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
	color: var(--text-color);
	border-bottom-color: var(--text-color);
}

.hub-project-info__toolbar {
	display: flex;
	align-items: center;
	justify-content: flex-end;
	gap: 14px;
	margin-bottom: 14px;
}

.hub-project-info__section {
	margin-bottom: 16px;
}

.hub-project-info__section:last-child {
	margin-bottom: 0;
}

.hub-project-info__section-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	margin-bottom: 10px;
}

.hub-project-info__section-head .hub-card__title {
	margin-bottom: 0;
}

.hub-info-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
	gap: 14px 18px;
	margin: 0;
}

.hub-info-grid dt {
	font-size: var(--text-xs);
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
}

.hub-info-grid dd {
	margin: 2px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
}

.hub-project-info__text {
	margin: 14px 0 0;
	font-size: var(--text-sm);
	color: var(--text-color);
	white-space: pre-wrap;
}

.hub-project-info__image-row {
	margin-bottom: 14px;
}

.hub-project-info__image {
	width: 96px;
	height: 96px;
	border-radius: var(--border-radius-lg);
	object-fit: cover;
	border: 1px solid var(--border-color);
}

.hub-project-info__list {
	list-style: none;
	margin: 0;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.hub-project-info__list li {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 8px 10px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	font-size: var(--text-sm);
}

.hub-project-info__list-role {
	color: var(--text-muted);
	flex: 0 0 auto;
	min-width: 140px;
}

.hub-project-info__list-name {
	flex: 1;
	color: var(--text-color);
}
</style>
