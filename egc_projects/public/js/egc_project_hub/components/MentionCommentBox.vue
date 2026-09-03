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

     Mentions are scoped to `project`'s own Directory — the same "Directory people STRICTLY" rule
     every other person-picker in this app already enforces (directory_helpers.js), not Frappe's
     stock site-wide `get_names_for_mentions`. There is no clean per-instance override point for
     this: ControlTextEditor.get_mention_options() only reads `this.mention_search_method`, a
     dotted method-path string Quill's own module calls via `frappe.xcall(method, {search_term})`
     — nothing but the typed text ever reaches the server, no room to thread a project id through.
     So this replaces `get_mention_options` on the shared `ControlTextEditor` PROTOTYPE for the
     single synchronous instant `make_control()` actually constructs the Quill instance (mention
     module wiring happens once, inside that constructor call, and is fixed for the control's
     lifetime after) — then restores the original immediately in a `finally`, before anything else
     can run. Safe specifically because JS is single-threaded and construction is fully
     synchronous: there is no `await` between the patch and the restore, so no other comment box
     anywhere on the page can observe the patched version. The candidate list itself, and the
     `{id, value, link, is_group}` item shape `quill-mention`'s own blot insertion expects, are
     taken directly from `frappe.desk.search.get_names_for_mentions`'s own return shape
     (frappe/desk/search.py) — same wire format, just a Directory-filtered source instead of a
     site-wide one. -->
<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from "vue";
import { get_directory } from "./directory_api";

const props = defineProps({
	project: { type: String, required: true },
	posting: { type: Boolean, default: false },
});
const emit = defineEmits(["submit"]);

const containerRef = ref(null);
let control = null;

async function get_directory_mention_candidates() {
	const rows = await get_directory(props.project).catch(() => []);
	// Only rows with a real login (`person`) — a stakeholder with no User can't be @mentioned;
	// there's nobody to notify.
	return rows
		.filter((r) => r.person)
		.map((r) => ({
			id: r.person,
			value: r.party_name || r.person,
			link: `/app/user/${encodeURIComponent(r.person)}`,
			is_group: false,
		}));
}

onMounted(async () => {
	const candidates = await get_directory_mention_candidates();

	const ControlTextEditor = frappe.ui.form.ControlTextEditor;
	const original_get_mention_options = ControlTextEditor.prototype.get_mention_options;
	ControlTextEditor.prototype.get_mention_options = function () {
		return {
			allowedChars: /^[\p{L}0-9_]*$/u,
			mentionDenotationChars: ["@"],
			isolateCharacter: true,
			source(search_term, renderList) {
				const term = (search_term || "").toLowerCase();
				const matches = term ? candidates.filter((c) => c.value.toLowerCase().includes(term)) : candidates;
				renderList(matches, search_term);
			},
			renderItem(item) {
				return item.value;
			},
		};
	};
	try {
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
	} finally {
		ControlTextEditor.prototype.get_mention_options = original_get_mention_options;
	}
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
	<!-- `comment-box`, not a made-up class: Frappe's own footer.js appends this exact control
	     into a `.comment-box` ancestor, and desk/form.scss's ONLY ql-editor override targeted
	     at it (`.comment-box .comment-input-container .frappe-control .ql-editor { min-height:
	     24px; ... }`) is what shrinks the control back down from the generic 100px every
	     `.ql-bubble .ql-editor` gets (common/quill.scss) — without this exact class name that
	     override never matches, and the editor renders at a jarring 100px minimum height with a
	     single line of text stranded at the top. Using Frappe's real class here instead of a
	     `hub-`-prefixed one of this app's own is what makes it look like the native desk comment
	     box, not a coincidence of similar CSS. -->
	<div ref="containerRef" class="comment-box"></div>
</template>
