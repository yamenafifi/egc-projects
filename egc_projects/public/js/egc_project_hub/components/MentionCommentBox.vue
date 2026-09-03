<!-- Shared comment composer for Submittal/Document/Activity detail pages — wraps Frappe's OWN
     native comment control (`frappe.ui.form.ControlComment`, fieldtype "Comment"), the exact
     Quill rich-text-plus-mentions widget every standard desk form's Timeline already uses
     (frappe/public/js/frappe/form/footer/footer.js's own `make_comment_box()`) — full toolbar
     (bold/italic/underline/strike/quote/code/link/image/lists/align/clear), @mentions, the same
     avatar-plus-button chrome. Deliberately NOT a hand-rolled reimplementation: a first attempt
     at that landed short of what this control already does for free, and re-derived unsafely
     what Frappe's own `sanitize_html()` (Comment.validate, frappe core) already guarantees about
     stored content — this wraps the real thing instead.

     Constructed standalone, no bound Form/Document — `frappe.ui.form.make_control` supports this
     natively (`BaseControl.get_status()` explicitly resolves to "Write" with no frm/doctype, "like
     in case of a dialog box"), and it's not a novel use: frappe core's own Print Format Builder
     (`LetterHeadEditor.vue`, a genuine Vue 3 SFC) builds this exact control the same way, and the
     portal Discussions page does too outside desk entirely. `controls.bundle.js` (where
     ControlComment lives) is already loaded here via Desk's own `app_include_js` — this page runs
     inside `/app`, so `frappe.ui.form.make_control` is already global, no `frappe.require` needed.

     Mentions here use Frappe's own stock `frappe.desk.search.get_names_for_mentions` — site-wide,
     not scoped to this project's Directory the way every other person-picker in this app
     deliberately is (directory_helpers.js). That's a real, known gap from this app's own
     "Directory people STRICTLY" convention, kept for now because ControlComment has no clean
     override point for the mention *source* itself (only for the search method's dotted path,
     which Quill calls with nothing but the typed search text — no room to thread a project id
     through it without hacking Quill's own module lifecycle). Flagged, not silently decided. -->
<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from "vue";

const props = defineProps({
	posting: { type: Boolean, default: false },
});
const emit = defineEmits(["submit"]);

const containerRef = ref(null);
let control = null;

onMounted(() => {
	control = frappe.ui.form.make_control({
		parent: containerRef.value,
		render_input: true,
		only_input: true,
		enable_mentions: true,
		df: { fieldtype: "Comment", fieldname: "comment" },
		on_submit: (value) => {
			if (!strip_html(value || "").trim() && !(value || "").includes("img")) return;
			emit("submit", value);
		},
	});
});

onBeforeUnmount(() => {
	control?.comment_wrapper?.remove();
});

watch(
	() => props.posting,
	(is_posting) => {
		if (!control) return;
		if (is_posting) control.disable();
		else control.enable();
	}
);

function clear() {
	control?.clear();
}

defineExpose({ clear });
</script>

<template>
	<div ref="containerRef" class="hub-comment-box"></div>
</template>
