<!-- Project Information panel (ARCHITECTURE_V2.md §1/§2/§3/§4) — WP-09's Hub-integrated view of
`EGC Project Profile`. Self-contained: only needs `project`, loads its own data and its own
`edit_profile` permission via `get_project_context`/`get_project_profile`. Never queries a
DocType directly — every round trip goes through `../api.js`, same rule as every other Hub tab.

Integration contract for the Hub header/shell package:

  Props:  project: String (required) — the ERPNext Project name, same value every other tab
          component already receives as `:project="route.project"`.
  Usage:  <ProjectInfoTab :project="project" />

  Fully self-contained beyond that one prop — it fetches its own data (get_project_profile) and
  its own edit permission (get_project_context().permissions.edit_profile), so no `:context`
  prop is required (harmless to pass; simply unused). Wiring a "Project Details" entry point
  into the Hub is therefore either:
    (a) a new tab — add "project-info" to useHubRoute.js's TABS and to EgcProjectHub.vue's
        tab_component/TAB_LABELS maps, or
    (b) a header button/link (e.g. in HubHeader.vue) that toggles a panel/modal rendering
        <ProjectInfoTab :project="route.project" />.
  Both are one-line-per-file additions in files this package does not own. -->
<script setup>
import { ref, computed, watch } from "vue";
import { get_project_context, get_project_profile, save_project_profile } from "../api";
import { useHubResource } from "../composables/useHubResource";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import ProjectInfoField from "./ProjectInfoField.vue";
import ProjectInfoStakeholderList from "./ProjectInfoStakeholderList.vue";
import ProjectInfoEquipmentList from "./ProjectInfoEquipmentList.vue";

const props = defineProps({
	project: { type: String, required: true },
});

// Mirrors constants.py's PROJECT_STAGES/SECTORS/DELIVERY_METHODS/CONTRACT_TYPES — that file is
// lead-owned and Python-only, so the option lists are restated here, the same way status-colour
// maps already mirror constants.py's status enums elsewhere in this Hub (useStatusColor.js).
const PROJECT_STAGES = ["Design", "Procurement", "Construction", "Commissioning", "Closeout", "Warranty"];
const SECTORS = ["Healthcare", "Industrial", "Commercial", "Infrastructure", "Other"];
const DELIVERY_METHODS = ["Design-Bid-Build", "Design-Build", "EPC", "Turnkey", "Other"];
const CONTRACT_TYPES = ["Lump Sum", "Unit Price", "Cost Plus", "Time & Material", "Other"];

const GENERAL_FIELDS = [
	{ key: "project_code", label: __("Project Code"), type: "text" },
	{ key: "project_stage", label: __("Project Stage"), type: "select", options: PROJECT_STAGES },
	{ key: "sector", label: __("Sector"), type: "select", options: SECTORS },
	{ key: "delivery_method", label: __("Delivery Method"), type: "select", options: DELIVERY_METHODS },
	{ key: "contract_type", label: __("Contract Type"), type: "select", options: CONTRACT_TYPES },
	{ key: "contract_value", label: __("Contract Value"), type: "currency" },
];
const DESCRIPTION_FIELDS = [
	{ key: "project_description", label: __("Project Description"), type: "textarea" },
	{ key: "work_scope", label: __("Work Scope"), type: "richtext" },
];
const SITE_FIELDS = [
	{ key: "country", label: __("Country"), type: "link", doctype: "Country" },
	{ key: "region", label: __("Region"), type: "text" },
	{ key: "city", label: __("City"), type: "text" },
	{ key: "address", label: __("Address"), type: "textarea" },
	{ key: "latitude", label: __("Latitude"), type: "number" },
	{ key: "longitude", label: __("Longitude"), type: "number" },
	{ key: "time_zone", label: __("Time Zone"), type: "text" },
	{ key: "site_contact_name", label: __("Site Contact Name"), type: "text" },
	{ key: "site_contact_phone", label: __("Site Contact Phone"), type: "text" },
	{ key: "site_contact_email", label: __("Site Contact Email"), type: "text" },
];
const DATE_FIELDS = [
	{ key: "contract_date", label: __("Contract Date"), type: "date" },
	{ key: "forecast_completion_date", label: __("Forecast Completion Date"), type: "date" },
	{ key: "warranty_start_date", label: __("Warranty Start Date"), type: "date" },
	{ key: "dlp_end_date", label: __("DLP End Date"), type: "date" },
];

async function load() {
	// One resource, two calls: `get_project_context` is the authority on whether a Profile row
	// exists at all (`profile: null`) and on `edit_profile`; `get_project_profile` is always the
	// full editable shape, including its own graceful empty default. Both are gated identically
	// (project read), so they succeed or fail together — a single loading/error state is enough.
	const [profile, context] = await Promise.all([
		get_project_profile(props.project),
		get_project_context(props.project),
	]);
	return {
		profile,
		profile_exists: Boolean(context.profile),
		can_edit: Boolean(context.permissions && context.permissions.edit_profile),
		currency: context.currency || "",
	};
}

const { data, loading, error, reload } = useHubResource(load);
watch(() => props.project, reload, { immediate: true });

const editing = ref(false);
const draft = ref(null);
const saving = ref(false);
const save_error = ref("");

function start_edit() {
	draft.value = JSON.parse(JSON.stringify(data.value.profile));
	save_error.value = "";
	editing.value = true;
}

function cancel_edit() {
	editing.value = false;
	draft.value = null;
	save_error.value = "";
}

function set_field(key, value) {
	draft.value[key] = value;
}

async function save() {
	saving.value = true;
	save_error.value = "";
	try {
		const saved = await save_project_profile(props.project, draft.value);
		data.value.profile = saved;
		data.value.profile_exists = true;
		editing.value = false;
		draft.value = null;
	} catch (e) {
		save_error.value = e.message || String(e);
	} finally {
		saving.value = false;
	}
}

const view_or_draft = computed(() => (editing.value ? draft.value : data.value?.profile));

// project_image is handled outside the generic ProjectInfoField renderer: it needs Frappe's
// upload dialog, not a text/select/date control.
function upload_image() {
	new frappe.ui.FileUploader({
		folder: "Home",
		on_success: (file) => set_field("project_image", file.file_url),
	});
}
function remove_image() {
	set_field("project_image", "");
}
</script>

<template>
	<div class="hub-project-info">
		<LoadingState v-if="loading" :rows="8" />
		<ErrorState v-else-if="error" :message="error" @retry="reload" />

		<EmptyState
			v-else-if="!data.profile_exists && !editing"
			:title="__('No project information yet')"
			:description="
				__(
					'Record the general, site, stakeholder, schedule and equipment details for this project.'
				)
			"
			:action-label="data.can_edit ? __('Add Project Information') : ''"
			@action="start_edit"
		/>

		<template v-else>
			<div class="hub-project-info__toolbar">
				<div v-if="save_error" class="hub-project-info__save-error">{{ save_error }}</div>
				<div class="hub-project-info__actions">
					<template v-if="!editing">
						<button
							v-if="data.can_edit"
							type="button"
							class="btn btn-sm btn-default"
							@click="start_edit"
						>
							{{ __("Edit") }}
						</button>
					</template>
					<template v-else>
						<button type="button" class="btn btn-sm btn-default" :disabled="saving" @click="cancel_edit">
							{{ __("Cancel") }}
						</button>
						<button type="button" class="btn btn-sm btn-primary" :disabled="saving" @click="save">
							{{ saving ? __("Saving…") : __("Save") }}
						</button>
					</template>
				</div>
			</div>

			<!-- General -->
			<section class="hub-card hub-project-info__section">
				<div class="hub-card__title">{{ __("General") }}</div>
				<div class="hub-project-info__image-row">
					<img
						v-if="view_or_draft.project_image"
						:src="view_or_draft.project_image"
						class="hub-project-info__image"
						:alt="__('Project image')"
					/>
					<div v-else-if="!editing" class="hub-project-info__image hub-project-info__image--placeholder">
						{{ __("No image") }}
					</div>
					<div v-if="editing" class="hub-project-info__image-actions">
						<button type="button" class="btn btn-xs btn-default" @click="upload_image">
							{{ __("Upload Image") }}
						</button>
						<button
							v-if="draft.project_image"
							type="button"
							class="btn btn-xs btn-default"
							@click="remove_image"
						>
							{{ __("Remove") }}
						</button>
					</div>
				</div>
				<div class="hub-info-grid">
					<ProjectInfoField
						v-for="f in GENERAL_FIELDS"
						:key="f.key"
						:field="f"
						:model-value="view_or_draft[f.key]"
						:editing="editing"
						:currency="data.currency"
						@update:model-value="(v) => set_field(f.key, v)"
					/>
				</div>
				<div class="hub-info-grid hub-info-grid--stack">
					<ProjectInfoField
						v-for="f in DESCRIPTION_FIELDS"
						:key="f.key"
						:field="f"
						:model-value="view_or_draft[f.key]"
						:editing="editing"
						@update:model-value="(v) => set_field(f.key, v)"
					/>
				</div>
			</section>

			<!-- Parties -->
			<section class="hub-card hub-project-info__section">
				<div class="hub-card__title">{{ __("Parties") }}</div>
				<ProjectInfoStakeholderList
					:model-value="view_or_draft.stakeholders"
					:editing="editing"
					@update:model-value="(v) => set_field('stakeholders', v)"
				/>
			</section>

			<!-- Site -->
			<section class="hub-card hub-project-info__section">
				<div class="hub-card__title">{{ __("Site") }}</div>
				<div class="hub-info-grid">
					<ProjectInfoField
						v-for="f in SITE_FIELDS"
						:key="f.key"
						:field="f"
						:model-value="view_or_draft[f.key]"
						:editing="editing"
						@update:model-value="(v) => set_field(f.key, v)"
					/>
				</div>
			</section>

			<!-- Dates -->
			<section class="hub-card hub-project-info__section">
				<div class="hub-card__title">{{ __("Dates") }}</div>
				<div class="hub-info-grid">
					<ProjectInfoField
						v-for="f in DATE_FIELDS"
						:key="f.key"
						:field="f"
						:model-value="view_or_draft[f.key]"
						:editing="editing"
						@update:model-value="(v) => set_field(f.key, v)"
					/>
				</div>
			</section>

			<!-- Healthcare / Equipment -->
			<section class="hub-card hub-project-info__section">
				<div class="hub-card__title">{{ __("Healthcare / Equipment") }}</div>
				<ProjectInfoEquipmentList
					:model-value="view_or_draft.equipment_items"
					:editing="editing"
					:project="project"
					@update:model-value="(v) => set_field('equipment_items', v)"
				/>
			</section>
		</template>
	</div>
</template>

<style scoped>
.hub-project-info__toolbar {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	margin-bottom: 14px;
}

.hub-project-info__actions {
	display: flex;
	gap: 8px;
	margin-left: auto;
}

.hub-project-info__save-error {
	color: var(--red-500, var(--text-on-red));
	font-size: var(--text-sm);
}

.hub-project-info__section {
	margin-bottom: 16px;
}

.hub-project-info__section:last-child {
	margin-bottom: 0;
}

.hub-info-grid {
	display: grid;
	grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
	gap: 14px 18px;
}

.hub-info-grid--stack {
	grid-template-columns: 1fr;
	margin-top: 14px;
}

.hub-project-info__image-row {
	display: flex;
	align-items: center;
	gap: 14px;
	margin-bottom: 14px;
}

.hub-project-info__image {
	width: 84px;
	height: 84px;
	border-radius: var(--border-radius-lg);
	object-fit: cover;
	border: 1px solid var(--border-color);
}

.hub-project-info__image--placeholder {
	display: flex;
	align-items: center;
	justify-content: center;
	font-size: var(--text-xs);
	color: var(--text-muted);
	background: var(--control-bg);
	text-align: center;
	padding: 4px;
}

.hub-project-info__image-actions {
	display: flex;
	gap: 8px;
}
</style>

<!-- Unscoped: shared by ProjectInfoStakeholderList.vue / ProjectInfoEquipmentList.vue, which
     render their own `.hub-form-field` rows but have no other common ancestor style block —
     same "shared shell CSS lives once, near the feature root" pattern EgcProjectHub.vue itself
     uses for .hub-table / .hub-toolbar. -->
<style>
.hub-form-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
	min-width: 0;
}

.hub-form-field label {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
}

.hub-form-field input[type="text"],
.hub-form-field input[type="date"],
.hub-form-field input[type="number"],
.hub-form-field select,
.hub-form-field textarea {
	font-size: var(--text-sm);
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	background: var(--fg-color);
	color: var(--text-color);
	padding: 5px 8px;
	min-height: 30px;
	width: 100%;
}

.hub-form-field textarea {
	min-height: 60px;
	resize: vertical;
}
</style>
