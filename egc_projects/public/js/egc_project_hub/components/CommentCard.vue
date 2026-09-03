<!-- One comment, rendered and editable to match Frappe core's own Activity card (form_timeline.js
     `setup_comment_actions`, templates/timeline_message_box.html) — "You"/name + relative
     timestamp (`comment_when`, the same global Frappe's own card uses), an Edit link, and a "…"
     menu with Delete, both gated by the exact same rule core enforces (edit: comment's own author
     or Administrator; delete: author or System Manager) rather than the raw Comment doctype's own
     permission list (System Manager/Website Manager only, which would silently block anyone else
     editing their own words — see comments.py's own docstring on this). Shared by all three
     detail pages instead of tripling this markup+logic per page. -->
<script setup>
import { ref, computed, onBeforeUnmount } from "vue";
import { update_comment, delete_comment } from "./comments_api";
import { renderCommentHtml } from "./mention_render";
import MentionCommentBox from "./MentionCommentBox.vue";

const props = defineProps({
	comment: { type: Object, required: true },
	referenceDoctype: { type: String, required: true },
	referenceName: { type: String, required: true },
	project: { type: String, required: true },
});
const emit = defineEmits(["changed"]);

const editing = ref(false);
const saving = ref(false);
const menu_open = ref(false);
const editBoxRef = ref(null);

const is_own = computed(() => props.comment.owner === frappe.session.user);
const can_edit = computed(() => ["Administrator", props.comment.owner].includes(frappe.session.user));
const can_delete = computed(() => is_own.value || frappe.user.has_role("System Manager"));

function close_menu_on_outside_click(e) {
	if (!e.target.closest(".hub-comment-card__menu")) close_menu();
}

function toggle_menu() {
	if (menu_open.value) {
		close_menu();
		return;
	}
	menu_open.value = true;
	// Deferred so the click that just opened the menu doesn't immediately close it again —
	// this same click is still bubbling when the listener would otherwise fire.
	setTimeout(() => document.addEventListener("click", close_menu_on_outside_click), 0);
}

function close_menu() {
	menu_open.value = false;
	document.removeEventListener("click", close_menu_on_outside_click);
}

function start_edit() {
	close_menu();
	editing.value = true;
}

function cancel_edit() {
	editing.value = false;
}

async function save_edit() {
	const content = editBoxRef.value?.getValue() || "";
	if (!strip_html(content).trim() && !content.includes("img")) return;
	saving.value = true;
	try {
		await update_comment(props.referenceDoctype, props.referenceName, props.comment.name, content);
		editing.value = false;
		emit("changed");
	} catch (e) {
		frappe.msgprint({ title: __("Could Not Save"), message: e.message, indicator: "red" });
	} finally {
		saving.value = false;
	}
}

function confirm_delete() {
	close_menu();
	frappe.confirm(__("Delete this comment?"), async () => {
		try {
			await delete_comment(props.referenceDoctype, props.referenceName, props.comment.name);
			emit("changed");
		} catch (e) {
			frappe.msgprint({ title: __("Could Not Delete"), message: e.message, indicator: "red" });
		}
	});
}

// Returns a real `<span class="frappe-timestamp" data-timestamp="...">` — bound with v-html
// deliberately (comment_when's own output, not user content): a global setInterval already
// running as part of desk's own boot (pretty_date.js) rescans every such span every 60s and
// refreshes its text from data-timestamp, so this stays live ("2 minutes ago" -> "3 minutes
// ago") without this component doing anything further.
function format_when(value) {
	return value ? window.comment_when(value) : "";
}

onBeforeUnmount(() => document.removeEventListener("click", close_menu_on_outside_click));
</script>

<template>
	<div class="hub-comment-card">
		<div class="hub-comment-card__header">
			<strong>{{ is_own ? __("You") : comment.owner }}</strong>
			{{ __("commented") }}
			<span class="hub-comment-card__when" v-html="format_when(comment.creation)"></span>
			<span v-if="!editing" class="hub-comment-card__actions">
				<a v-if="can_edit" href="#" @click.prevent="start_edit">{{ __("Edit") }}</a>
				<span v-if="can_delete" class="hub-comment-card__menu">
					<button type="button" class="hub-comment-card__menu-btn" @click.stop="toggle_menu">…</button>
					<div v-if="menu_open" class="hub-comment-card__menu-list">
						<button type="button" @click="confirm_delete">{{ __("Delete") }}</button>
					</div>
				</span>
			</span>
		</div>

		<div v-if="!editing" class="hub-comment-card__body" v-html="renderCommentHtml(comment.content)"></div>
		<div v-else class="hub-comment-card__edit">
			<MentionCommentBox ref="editBoxRef" :project="project" no-wrapper :initial-value="comment.content" :posting="saving" @submit="save_edit" />
			<div class="hub-comment-card__edit-actions">
				<button type="button" class="btn btn-xs btn-primary" :disabled="saving" @click="save_edit">{{ __("Save") }}</button>
				<button type="button" class="btn btn-xs btn-default" :disabled="saving" @click="cancel_edit">{{ __("Discard") }}</button>
			</div>
		</div>
	</div>
</template>
