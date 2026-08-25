<!-- Generic Frappe Link control, same technique as ProjectLinkControl.vue but parametrised over
`doctype` — used everywhere Project Information needs a searchable Link (Country, Role, User,
Contact, Modality, Equipment Manufacturer, WBS Node) instead of a bare text input, so these
fields get the same search box, permissions and formatting as every native Desk form. -->
<script setup>
import { onMounted, ref, watch } from "vue";

const props = defineProps({
	modelValue: { type: String, default: "" },
	doctype: { type: String, required: true },
	placeholder: { type: String, default: "" },
	filters: { type: Object, default: null },
});
const emit = defineEmits(["update:modelValue"]);

const wrapper = ref(null);
let control = null;

onMounted(() => {
	control = frappe.ui.form.make_control({
		parent: wrapper.value,
		df: {
			fieldtype: "Link",
			fieldname: "value",
			label: "",
			options: props.doctype,
			placeholder: props.placeholder,
			get_query: props.filters ? () => ({ filters: props.filters }) : undefined,
			change() {
				// See ProjectLinkControl.vue: the underlying awesomplete input can still fire
				// after this component has unmounted (e.g. a row was just removed), so
				// `control` is re-read rather than closed over.
				if (!control) return;
				const value = control.get_value();
				if (value !== props.modelValue) emit("update:modelValue", value || "");
			},
		},
		render_input: true,
		only_input: true,
	});
	control.refresh();
	if (props.modelValue) control.set_value(props.modelValue);
});

watch(
	() => props.modelValue,
	(value) => {
		if (control && control.get_value() !== (value || "")) control.set_value(value || "");
	}
);
</script>

<template>
	<div ref="wrapper" class="hub-link-field"></div>
</template>

<style scoped>
.hub-link-field :deep(.form-control) {
	width: 100%;
	font-size: var(--text-sm);
}
</style>
