<!-- Editable repeater for EGC Project Profile.stakeholders (ARCHITECTURE_V2.md §2). A role with
no `user` is a genuine, valid state (a pure external party with no Frappe login) — never an
error — but it means that stakeholder cannot be a live in-app reviewer later, so the "No login"
badge below is deliberate, not a validation warning. -->
<script setup>
import { ref, watch } from "vue";
import HubLinkField from "./HubLinkField.vue";
import EmptyState from "./EmptyState.vue";

const props = defineProps({
	modelValue: { type: Array, default: () => [] },
	editing: { type: Boolean, default: false },
});
const emit = defineEmits(["update:modelValue"]);

// A locally-owned copy, not a read of `props.modelValue` at patch time. Vue re-renders (and
// therefore prop propagation back down from the parent) are batched onto a microtask, so two
// field edits on the same row fired in quick succession — fast typing across fields, a paste,
// or scripted entry — would otherwise both read the SAME stale `props.modelValue` snapshot and
// each write back a whole-array replacement, silently dropping whichever edit lost the race.
// Mutating `rows` in place keeps every edit visible to the next one immediately, no matter how
// close together they land; `watch` only needs to resync when the parent hands us a genuinely
// different array (e.g. Cancel discards the draft, or a fresh edit session starts).
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
	rows.value.push({ role: "", party_name: "", organization: "", user: "", contact: "", email: "", phone: "", is_primary: 0 });
	emit("update:modelValue", rows.value);
}

function remove_row(index) {
	rows.value.splice(index, 1);
	emit("update:modelValue", rows.value);
}
</script>

<template>
	<div class="hub-repeater">
		<EmptyState
			v-if="!editing && !rows.length"
			:title="__('No stakeholders recorded')"
			:description="__('Add the client, consultant, contractor and internal team assigned to this project.')"
		/>

		<template v-else>
			<div v-if="!editing" class="hub-repeater__view">
				<div v-for="(row, index) in rows" :key="index" class="hub-stakeholder-card">
					<div class="hub-stakeholder-card__main">
						<span class="hub-stakeholder-card__role">{{ row.role || "—" }}</span>
						<span class="hub-stakeholder-card__name">{{ row.party_name }}</span>
						<span v-if="row.organization" class="hub-stakeholder-card__org">{{ row.organization }}</span>
						<span v-if="row.is_primary" class="indicator-pill blue hub-stakeholder-card__primary">{{
							__("Primary")
						}}</span>
					</div>
					<div class="hub-stakeholder-card__contact">
						<span v-if="row.user">{{ row.user }}</span>
						<span v-else class="indicator-pill gray">{{ __("No login") }}</span>
						<span v-if="row.email">{{ row.email }}</span>
						<span v-if="row.phone">{{ row.phone }}</span>
					</div>
				</div>
			</div>

			<div v-else class="hub-repeater__edit">
				<div v-for="(row, index) in rows" :key="index" class="hub-stakeholder-row">
					<div class="hub-form-field">
						<label>{{ __("Role") }}</label>
						<HubLinkField
							:model-value="row.role"
							doctype="EGC Stakeholder Role"
							:placeholder="__('Select role…')"
							@update:model-value="(v) => update_row(index, { role: v })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("Party Name") }}</label>
						<input
							type="text"
							:value="row.party_name"
							:placeholder="__('Person or organisation')"
							@input="update_row(index, { party_name: $event.target.value })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("Organization") }}</label>
						<input
							type="text"
							:value="row.organization"
							@input="update_row(index, { organization: $event.target.value })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("User") }}</label>
						<HubLinkField
							:model-value="row.user"
							doctype="User"
							:placeholder="__('Frappe login, if any…')"
							@update:model-value="(v) => update_row(index, { user: v })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("Contact") }}</label>
						<HubLinkField
							:model-value="row.contact"
							doctype="Contact"
							@update:model-value="(v) => update_row(index, { contact: v })"
						/>
					</div>
					<div class="hub-form-field">
						<label>{{ __("Email") }}</label>
						<input type="text" :value="row.email" @input="update_row(index, { email: $event.target.value })" />
					</div>
					<div class="hub-form-field">
						<label>{{ __("Phone") }}</label>
						<input type="text" :value="row.phone" @input="update_row(index, { phone: $event.target.value })" />
					</div>
					<div class="hub-form-field hub-form-field--check">
						<label>
							<input
								type="checkbox"
								:checked="!!row.is_primary"
								@change="update_row(index, { is_primary: $event.target.checked ? 1 : 0 })"
							/>
							{{ __("Primary") }}
						</label>
					</div>
					<button
						type="button"
						class="btn btn-xs btn-default hub-repeater__remove"
						:aria-label="__('Remove stakeholder')"
						@click="remove_row(index)"
					>
						{{ __("Remove") }}
					</button>
				</div>
			</div>
		</template>

		<button v-if="editing" type="button" class="btn btn-sm btn-default hub-repeater__add" @click="add_row">
			{{ __("+ Add Stakeholder") }}
		</button>
	</div>
</template>

<style scoped>
.hub-repeater__view {
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.hub-stakeholder-card {
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 10px 14px;
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	justify-content: space-between;
	gap: 8px;
}

.hub-stakeholder-card__main {
	display: flex;
	align-items: center;
	gap: 10px;
	flex-wrap: wrap;
}

.hub-stakeholder-card__role {
	font-size: var(--text-xs);
	font-weight: 600;
	text-transform: uppercase;
	letter-spacing: 0.03em;
	color: var(--text-muted);
}

.hub-stakeholder-card__name {
	font-weight: 500;
	color: var(--text-color);
}

.hub-stakeholder-card__org {
	color: var(--text-muted);
	font-size: var(--text-sm);
}

.hub-stakeholder-card__contact {
	display: flex;
	align-items: center;
	gap: 12px;
	font-size: var(--text-sm);
	color: var(--text-muted);
}

.hub-repeater__edit {
	display: flex;
	flex-direction: column;
	gap: 14px;
}

.hub-stakeholder-row {
	position: relative;
	display: grid;
	grid-template-columns: repeat(4, minmax(150px, 1fr));
	gap: 10px 14px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	padding: 14px 40px 14px 14px;
	background: var(--fg-color);
}

.hub-form-field--check {
	align-self: end;
}

.hub-form-field--check label {
	display: flex;
	align-items: center;
	gap: 6px;
	font-weight: 400;
	color: var(--text-color);
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
