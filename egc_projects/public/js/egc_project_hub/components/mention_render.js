// Renders a Comment's `content` (egc_projects/egc_projects/comments.py, backed by Frappe core's
// own `Comment` doctype) safely as HTML for `v-html`.
//
// `content` never reaches storage as whatever a caller sent — Comment.validate() (Frappe core,
// frappe/core/doctype/comment/comment.py) unconditionally runs it through `sanitize_html()`
// (frappe/utils/html_utils.py) on every save, old comments and new alike: a real HTML parser
// (`nh3`, a Rust binding of the `ammonia` sanitizer) that strips anything not on its own
// allowlist and re-serializes the rest as well-formed, safe HTML. So `content` at rest is
// already genuinely safe markup, not raw user input — a second escape pass here would be
// redundant at best and actively wrong at worst (confirmed directly: it double-escaped already-
// safe entities sanitize_html had produced, corrupting the display of anything that wasn't a
// mention). `v-html`-ing it directly is the correct move, not a shortcut around one.
//
// The one thing this still does: sanitize_html's own allowlist includes `data-*` generically
// (`generic_attribute_prefixes={"data-"}` in html_utils.py) specifically so a `<span
// class="mention" data-id="...">` — the exact shape MentionCommentBox.vue's own composer
// produces, and the shape Frappe core's own `notify_mentions` (frappe/desk/notifications.py)
// scans stored content for to fire the mention notification — survives sanitization intact. This
// adds this app's own visual styling on top of that survived span, without touching or
// re-interpreting anything else in the content.

/** @returns {string} safe HTML for `v-html` — content is already sanitized; this only re-tags
 * Frappe's own `.mention` spans with this app's own chip styling. */
export function renderCommentHtml(content) {
	const container = document.createElement("div");
	container.innerHTML = content ?? "";
	container.querySelectorAll(".mention").forEach((el) => el.classList.add("hub-mention-chip"));
	return container.innerHTML;
}
