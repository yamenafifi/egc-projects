// Opens Frappe's own native "New Email" dialog (frappe.views.CommunicationComposer,
// frappe/public/js/frappe/views/communication.js) against an arbitrary EGC record — the full
// widget verbatim: To/CC/BCC, Schedule Send At, Email Template picker, the same rich-text editor
// MentionCommentBox.vue wraps, Send-me-a-copy, Send Read Receipt, Attach Document Print (+ print
// format/language), and attachments. Nothing here reimplements any of that.
//
// Constructed standalone, no bound Form — confirmed viable and precedented directly in Frappe
// core: frappe/public/js/frappe/request.js's own error-report flow builds this exact class with
// nothing but `{subject, recipients, message, doc: {doctype, name}}`, no `frm` anywhere. Every
// frm-dependent piece of the composer already degrades gracefully without one (per its own
// source): the doc-title/last-email subject autofill is skipped (this is why the subject is
// passed in explicitly below, in the same "{title} (#{reference_name})" shape Frappe's own
// frm-bound autofill would have produced), and "Attach Document Print" quietly hides its own
// print-format picker rather than erroring. The actual permission gate is server-side regardless
// (frappe.has_permission(doctype, doc=name, ptype="email"), core/doctype/communication/email.py)
// — a client without `frm` was never the thing keeping this safe.

export function openNewEmail({ referenceDoctype, referenceName, title, onClose }) {
	const composer = new frappe.views.CommunicationComposer({
		doc: { doctype: referenceDoctype, name: referenceName },
		subject: title ? `${title} (#${referenceName})` : referenceName,
	});
	// No send-succeeded callback exists on this class (checked its source directly) — closing the
	// dialog either way (sent or discarded) is the closest reliable signal to refresh the
	// activity feed on, and a reload that finds nothing new is harmless. `on_hide` is
	// frappe.ui.Dialog's own real hook for this (dialog.js: `me.on_hide && me.on_hide()`, called
	// from its "hide.bs.modal" listener) — but CommunicationComposer's own setup_subject_and_recipients()
	// already assigns dialog.on_hide itself, to save an in-progress draft for recall if reopened
	// (get_last_edited_communication) — overwriting it outright would silently break that.
	// Chaining preserves it.
	if (onClose && composer.dialog) {
		const existing_on_hide = composer.dialog.on_hide;
		composer.dialog.on_hide = () => {
			existing_on_hide?.();
			onClose();
		};
	}
}
