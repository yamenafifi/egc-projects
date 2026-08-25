<!-- One labelled field, view or edit, for whichever `field.type` it declares. Shared by every
group in ProjectInfoTab.vue so a new Project Information field is one entry in a field-def
array, not a hand-written pair of view/edit markup blocks. -->
<script setup>
import HubLinkField from "./HubLinkField.vue";

const props = defineProps({
	field: { type: Object, required: true }, // { key, label, type, options?, doctype? }
	modelValue: { default: null },
	editing: { type: Boolean, default: false },
	currency: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue"]);

function on_input(event) {
	emit("update:modelValue", event.target.value);
}

function display_value() {
	const value = props.modelValue;
	if (value === null || value === undefined || value === "") return "—";
	if (props.field.type === "date") return frappe.datetime.str_to_user(value);
	// format_currency() returns a plain string, safe for text interpolation (unlike
	// frappe.format(), which wraps Currency in a <div> meant for v-html — see FinancialsTab.vue).
	if (props.field.type === "currency") return format_currency(value, props.currency);
	return value;
}
</script>

<template>
	<div
		class="hub-info-field"
		:class="{ 'hub-info-field--wide': field.type === 'textarea' || field.type === 'richtext' }"
	>
		<label>{{ field.label }}</label>

		<template v-if="!editing">
			<!-- `work_scope` is a genuine Text Editor field (stored HTML) — v-html is the
			     correct rendering here, unlike a v-hooked frappe.format() string elsewhere. -->
			<div v-if="field.type === 'richtext'" class="hub-info-field__richtext" v-html="modelValue || '—'" />
			<div v-else class="hub-info-field__value">{{ display_value() }}</div>
		</template>

		<template v-else>
			<select v-if="field.type === 'select'" :value="modelValue || ''" @change="on_input">
				<option value="">{{ __("—") }}</option>
				<option v-for="opt in field.options" :key="opt" :value="opt">{{ opt }}</option>
			</select>
			<HubLinkField
				v-else-if="field.type === 'link'"
				:model-value="modelValue || ''"
				:doctype="field.doctype"
				@update:model-value="(v) => emit('update:modelValue', v)"
			/>
			<textarea
				v-else-if="field.type === 'textarea' || field.type === 'richtext'"
				rows="3"
				:value="modelValue"
				@input="on_input"
			/>
			<input v-else-if="field.type === 'date'" type="date" :value="modelValue" @input="on_input" />
			<input
				v-else-if="field.type === 'number' || field.type === 'currency'"
				type="number"
				step="any"
				:value="modelValue"
				@input="on_input"
			/>
			<input v-else type="text" :value="modelValue" @input="on_input" />
		</template>
	</div>
</template>

<style scoped>
.hub-info-field {
	display: flex;
	flex-direction: column;
	gap: 4px;
	min-width: 0;
}

.hub-info-field--wide {
	grid-column: 1 / -1;
}

.hub-info-field label {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
}

.hub-info-field__value {
	font-size: var(--text-sm);
	color: var(--text-color);
	min-height: 20px;
	word-break: break-word;
}

.hub-info-field__richtext {
	font-size: var(--text-sm);
	color: var(--text-color);
}

.hub-info-field__richtext :deep(p) {
	margin: 0 0 6px;
}

.hub-info-field__richtext :deep(p:last-child) {
	margin-bottom: 0;
}
</style>
