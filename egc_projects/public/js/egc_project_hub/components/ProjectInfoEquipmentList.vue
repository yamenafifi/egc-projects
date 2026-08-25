<!-- Editable repeater for EGC Project Profile.equipment_items (ARCHITECTURE_V2.md §3). Modality
and Equipment Manufacturer are Links to small, freely-extensible masters — "Siemens / Philips /
GE" is data on a row here, never a Select option or a doctype of its own. -->
<script setup>
import { ref, watch } from "vue";
import HubLinkField from "./HubLinkField.vue";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	editing: { type: Boolean, default: false },
	project: { type: String, required: true },
});
const emit = defineEmits(["update:modelValue"]);

// Local copy mutated in place, not a read of `props.modelValue` at patch time — see the
// identical comment in ProjectInfoStakeholderList.vue for why: prop propagation from the
// parent is batched onto a microtask, so two rapid edits on the same row would otherwise both
// read the same stale array and the second emit would silently overwrite the first.
const rows = ref([]);
watch(
	() => props.modelValue,
	(value) => {
		rows.value = (value || []).map((row) => ({ ...row }));
	},
	{ immediate: true }
);

function update_row(index, patch) {
	rows.value[index] = { ...rows.value[index], ...patch };
	emit("update:modelValue", rows.value);
}

function add_row() {
	rows.value.push({
		facility: "",
		department: "",
		modality: "",
		wbs_node: "",
		equipment_manufacturer: "",
		equipment_model: "",
		oem_reference: "",
		equipment_delivery_target: "",
		room_ready_target: "",
		oem_installation_target: "",
		commissioning_target: "",
		notes: "",
	});
	emit("update:modelValue", rows.value);
}

function remove_row(index) {
	rows.value.splice(index, 1);
	emit("update:modelValue", rows.value);
}

function format_date(value) {
	return value ? frappe.datetime.str_to_user(value) : "—";
}
</script>

<template>
	<div class="hub-repeater">
		<EmptyState
			v-if="!editing && !rows.length"
			:title="__('No equipment recorded')"
			:description="__('Track medical equipment — facility, modality, manufacturer and delivery milestones — for this project.')"
		/>

		<template v-else>
			<div v-if="!editing" class="hub-table-wrap">
				<table class="hub-table">
					<thead>
						<tr>
							<th>{{ __("Facility") }}</th>
							<th>{{ __("Department") }}</th>
							<th>{{ __("Modality") }}</th>
							<th>{{ __("Manufacturer") }}</th>
							<th>{{ __("Model") }}</th>
							<th>{{ __("Delivery Target") }}</th>
							<th>{{ __("Commissioning Target") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(row, index) in rows" :key="index">
							<td>{{ row.facility || "—" }}</td>
							<td>{{ row.department || "—" }}</td>
							<td>{{ row.modality || "—" }}</td>
							<td>{{ row.equipment_manufacturer || "—" }}</td>
							<td>{{ row.equipment_model || "—" }}</td>
							<td>{{ format_date(row.equipment_delivery_target) }}</td>
							<td>{{ format_date(row.commissioning_target) }}</td>
						</tr>
					</tbody>
				</table>
			</div>

			<div v-else class="hub-repeater__edit">
				<div v-for="(row, index) in rows" :key="index" class="hub-equipment-row">
					<div class="hub-form-field">
						<label>{{ __("Facility") }}</label>
						<input type="text" :value="row.facility" @input="update_row(index, { facility: $event.target.value })" />
					</div>
					<div class="hub-form-field">
						<label>{{ __("Department") }}</label>
						<input
							type="text"
							:value="row.department"
							@input="update_row(index, { department: $event.target.value })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("Modality") }}</label>
						<HubLinkField
							:model-value="row.modality"
							doctype="EGC Modality"
							@update:model-value="(v) => update_row(index, { modality: v })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("WBS Node") }}</label>
						<HubLinkField
							:model-value="row.wbs_node"
							doctype="EGC WBS Node"
							:filters="{ project }"
							:placeholder="__('Physical location, if any…')"
							@update:model-value="(v) => update_row(index, { wbs_node: v })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("Manufacturer") }}</label>
						<HubLinkField
							:model-value="row.equipment_manufacturer"
							doctype="EGC Equipment Manufacturer"
							@update:model-value="(v) => update_row(index, { equipment_manufacturer: v })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("Model") }}</label>
						<input
							type="text"
							:value="row.equipment_model"
							@input="update_row(index, { equipment_model: $event.target.value })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("OEM Reference") }}</label>
						<input
							type="text"
							:value="row.oem_reference"
							@input="update_row(index, { oem_reference: $event.target.value })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("Equipment Delivery Target") }}</label>
						<input
							type="date"
							:value="row.equipment_delivery_target"
							@input="update_row(index, { equipment_delivery_target: $event.target.value })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("Room Ready Target") }}</label>
						<input
							type="date"
							:value="row.room_ready_target"
							@input="update_row(index, { room_ready_target: $event.target.value })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("OEM Installation Target") }}</label>
						<input
							type="date"
							:value="row.oem_installation_target"
							@input="update_row(index, { oem_installation_target: $event.target.value })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("Commissioning Target") }}</label>
						<input
							type="date"
							:value="row.commissioning_target"
							@input="update_row(index, { commissioning_target: $event.target.value })"
						/>
					</div>
					<div class="hub-form-field hub-form-field--wide">
						<label>{{ __("Notes") }}</label>
						<textarea rows="2" :value="row.notes" @input="update_row(index, { notes: $event.target.value })" />
					</div>
					<button
						type="button"
						class="btn btn-xs btn-default hub-repeater__remove"
						:aria-label="__('Remove equipment item')"
						@click="remove_row(index)"
					>
						{{ __("Remove") }}
					</button>
				</div>
			</div>
		</template>

		<button v-if="editing" type="button" class="btn btn-sm btn-default hub-repeater__add" @click="add_row">
			{{ __("+ Add Equipment") }}
		</button>
	</div>
</template>

<style scoped>
.hub-repeater__edit {
	display: flex;
	flex-direction: column;
	gap: 14px;
}

.hub-equipment-row {
	position: relative;
	display: grid;
	grid-template-columns: repeat(4, minmax(150px, 1fr));
	gap: 10px 14px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	padding: 14px 40px 14px 14px;
	background: var(--fg-color);
}

.hub-form-field--wide {
	grid-column: 1 / -1;
}

.hub-repeater__remove {
	position: absolute;
	top: 10px;
	right: 10px;
}

.hub-repeater__add {
	margin-top: 12px;
}
</style>
