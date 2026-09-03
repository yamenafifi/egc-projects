// Renders a Comment's `content` (egc_projects/egc_projects/comments.py, backed by Frappe core's
// own `Comment` doctype) safely as HTML for `v-html`.
//
// `content` never reaches storage as whatever a caller sent — Comment.validate() (Frappe core,
// frappe/core/doctype/comment/comment.py) unconditionally runs it through `sanitize_html()`
// (frappe/utils/html_utils.py) on every save, old comments and new alike: a real HTML parser
// (`nh3`, a Rust binding of the `ammonia` sanitizer) that strips anything not on its own
// allowlist and re-serializes the rest as well-formed, safe HTML — including MentionCommentBox.vue's
// own Quill-produced rich text (bold/italic/lists/links/...) and its `<span class="mention"
// data-id="...">` tags (`generic_attribute_prefixes={"data-"}` in html_utils.py specifically
// keeps `data-id` intact, since Frappe core's own `notify_mentions` needs that exact shape to
// fire the mention notification). So `content` at rest is already genuinely safe markup, not raw
// user input — `v-html`-ing it directly is correct, not a shortcut around one.
//
// No transform needed either: `.mention` and `.ql-editor` already have real, theme-aware CSS
// loaded globally on every desk page (frappe/public/scss/common/quill.scss) — this app doesn't
// need to invent its own chip styling on top, and doing so would just fight Frappe's own.

/** @returns {string} safe HTML for `v-html` — never bind `content` directly without this (keeps
 * a null-safe default and one documented place to point at for why this is safe). */
export function renderCommentHtml(content) {
	return content || "";
}
