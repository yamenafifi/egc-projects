<!-- Standard Frappe Link control against Project, reused for both the empty-state picker and
the header switcher. Uses frappe.ui.form.make_control so the search box, permissions and
formatting are exactly what every other Project field in Desk already does — the Hub itself
never queries the Project list directly. -->
<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps({
	modelValue: { type: String, default: "" },
	placeholder: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue"]);

const wrapper = ref(null);
let control = null;

onMounted(() => {
	control = frappe.ui.form.make_control({
		parent: wrapper.value,
		df: {
			fieldtype: "Link",
			fieldname: "project",
			label: "",
			options: "Project",
			placeholder: props.placeholder,
			change() {
				const value = control.get_value();
				if (value && value !== props.modelValue) emit("update:modelValue", value);
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

onBeforeUnmount(() => {
	control = null;
});
</script>

<template>
	<div ref="wrapper" class="hub-project-link"></div>
</template>

<style scoped>
.hub-project-link :deep(.form-control) {
	min-width: 220px;
}
</style>
