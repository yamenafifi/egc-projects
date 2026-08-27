<!-- Project Information — a READ-ONLY curated summary of the `custom_egc_*` fields that live
directly on the core `Project` doctype (project_custom_fields.py). There is no edit form here on
purpose: this data is edited on the native Project form's "EGC Project Info" tab, the same way
egc_hr's own Supervisors/Project Location fields already are — this tab exists only to give the
Hub a nicer read surface than the native form's raw layout, with a link out to actually edit. -->
<script setup>
import { computed, watch } from "vue";
import { get_project_info, get_project_context } from "../api";
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
		"country",
		"region",
		"city",
		"address",
		"time_zone",
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

function open_edit() {
	frappe.set_route("Form", "Project", props.project);
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}

function stakeholder_party(row) {
	return row.party_name || row.organization || "—";
}
</script>

<template>
	<div class="hub-project-info">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />

		<EmptyState
			v-else-if="!has_any_data"
			:title="__('No project information yet')"
			:description="
				__(
					'Classification, stakeholders, address and contract dates for this project live on its native form.'
				)
			"
			:action-label="data.can_edit ? __('Add on Project Form') : ''"
			@action="open_edit"
		/>

		<template v-else>
			<div class="hub-project-info__toolbar">
				<button v-if="data.can_edit" type="button" class="btn btn-sm btn-default" @click="open_edit">
					{{ __("Edit on Project Form") }}
				</button>
			</div>

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

			<section v-if="data.info.stakeholders.length" class="hub-card hub-project-info__section">
				<div class="hub-card__title">{{ __("Stakeholders") }}</div>
				<ul class="hub-project-info__list">
					<li v-for="(row, idx) in data.info.stakeholders" :key="idx">
						<span class="hub-project-info__list-role">{{ row.role }}</span>
						<span class="hub-project-info__list-name">{{ stakeholder_party(row) }}</span>
						<span v-if="row.is_primary" class="indicator-pill blue">{{ __("Primary") }}</span>
					</li>
				</ul>
			</section>

			<section class="hub-card hub-project-info__section">
				<div class="hub-card__title">{{ __("Address") }}</div>
				<dl class="hub-info-grid">
					<div>
						<dt>{{ __("Country") }}</dt>
						<dd>{{ data.info.country || "—" }}</dd>
					</div>
					<div>
						<dt>{{ __("Region") }}</dt>
						<dd>{{ data.info.region || "—" }}</dd>
					</div>
					<div>
						<dt>{{ __("City") }}</dt>
						<dd>{{ data.info.city || "—" }}</dd>
					</div>
					<div>
						<dt>{{ __("Address") }}</dt>
						<dd>{{ data.info.address || "—" }}</dd>
					</div>
					<div>
						<dt>{{ __("Time Zone") }}</dt>
						<dd>{{ data.info.time_zone || "—" }}</dd>
					</div>
				</dl>
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

			<section v-if="data.info.equipment_items.length" class="hub-card hub-project-info__section">
				<div class="hub-card__title">{{ __("Healthcare / Equipment") }}</div>
				<div class="hub-table-wrap">
					<table class="hub-table">
						<thead>
							<tr>
								<th>{{ __("Facility") }}</th>
								<th>{{ __("Modality") }}</th>
								<th>{{ __("Manufacturer") }}</th>
								<th>{{ __("Model") }}</th>
								<th>{{ __("Delivery Target") }}</th>
								<th>{{ __("Commissioning Target") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="(row, idx) in data.info.equipment_items" :key="idx">
								<td>{{ row.facility || "—" }}</td>
								<td>{{ row.modality || "—" }}</td>
								<td>{{ row.equipment_manufacturer || "—" }}</td>
								<td>{{ row.equipment_model || "—" }}</td>
								<td>{{ format_date(row.equipment_delivery_target) }}</td>
								<td>{{ format_date(row.commissioning_target) }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>
		</template>
	</div>
</template>

<style scoped>
.hub-project-info__toolbar {
	display: flex;
	justify-content: flex-end;
	margin-bottom: 14px;
}

.hub-project-info__section {
	margin-bottom: 16px;
}

.hub-project-info__section:last-child {
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
