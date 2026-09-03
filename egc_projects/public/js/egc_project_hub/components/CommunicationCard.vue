<!-- One sent/received email (Communication), rendered read-only — Frappe core's own Activity
     card doesn't offer inline edit/delete for emails the way it does for comments, so this stays
     simpler than CommentCard.vue on purpose, not an oversight. Status pill mirrors
     form_timeline.js's own `set_communication_doc_status` (Sent/Read/Error), reading the same
     `delivery_status` field the real read-receipt tracking pixel writes back to
     (frappe.core.doctype.communication.email.mark_email_as_seen). -->
<script setup>
import { renderCommentHtml } from "./mention_render";

defineProps({
	communication: { type: Object, required: true },
});

const STATUS_COLOR = {
	Read: "green",
	Sent: "blue",
	"Sending Queued": "orange",
	Error: "red",
};

function status_label(status) {
	return status || "Sent";
}

function status_color(status) {
	return STATUS_COLOR[status] || "blue";
}

// Real `<span class="frappe-timestamp">` HTML, bound with v-html deliberately — see
// CommentCard.vue's own note on this same helper.
function format_when(value) {
	return value ? window.comment_when(value) : "";
}
</script>

<template>
	<div class="hub-comment-card hub-comment-card--email">
		<div class="hub-comment-card__header">
			<strong>{{ communication.sender_full_name || communication.sender || communication.owner }}</strong>
			{{ __("sent an email") }}
			<span class="indicator-pill hub-comment-card__status" :class="status_color(communication.delivery_status)">
				{{ status_label(communication.delivery_status) }}
			</span>
			<span class="hub-comment-card__when" v-html="format_when(communication.creation)"></span>
		</div>
		<div class="hub-comment-card__email-meta">
			<strong>{{ __("Subject") }}:</strong> {{ communication.subject }}
			<span v-if="communication.recipients"> · <strong>{{ __("To") }}:</strong> {{ communication.recipients }}</span>
		</div>
		<div class="hub-comment-card__body" v-html="renderCommentHtml(communication.content)"></div>
	</div>
</template>
