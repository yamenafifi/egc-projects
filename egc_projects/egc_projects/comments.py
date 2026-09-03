"""Comments and Communications on any EGC record — Level 0 §7/§32: an external reviewer must be
able to add response comments, the same as any internal user. A thin, explicit wrapper around
Frappe's own `Comment`/`Communication` doctypes rather than a new comment system — this module
exists only because core has no whitelisted counterpart for LISTING a document's comments (or a
merged comment+email activity feed), and because listing them for an arbitrary reference doctype
needs the same explicit "can you even read this record" gate `add_comment` itself already
applies.

Generic by reference_doctype/reference_name, not tied to Submittals specifically — reusable for
Documents, Activities, and future RFIs/Inspections without a new module per record type.

Edit/delete permission on a Comment mirrors Frappe core's own exact rule (form_timeline.js's
`setup_comment_actions`), not the raw `Comment` doctype's own permission list — that list only
grants System Manager/Website Manager, which would silently block an ordinary internal user or
external reviewer from ever editing/deleting their OWN comment if called through
`frappe.client.delete`/`frappe.desk.form.utils.update_comment` directly. Reimplemented explicitly
here instead, on top of this module's own already-established "read access to the parent record,
verified server-side, then ignore_permissions for the actual write" pattern.
"""

from __future__ import annotations

import frappe


@frappe.whitelist()
def get_comments(reference_doctype: str, reference_name: str) -> list[dict]:
	frappe.has_permission(reference_doctype, "read", doc=reference_name, throw=True)

	return frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"comment_type": "Comment",
		},
		fields=["name", "content", "owner", "creation"],
		order_by="creation asc",
	)


@frappe.whitelist()
def get_activity(reference_doctype: str, reference_name: str) -> dict:
	"""Comments plus the real email thread (Communication) on this record, for a merged
	activity feed — the same two channels Frappe core's own Activity timeline shows by default
	(`only_communication` mode, form_timeline.js) before its version/like/share/assignment noise
	is added on top of them."""
	frappe.has_permission(reference_doctype, "read", doc=reference_name, throw=True)

	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"comment_type": "Comment",
		},
		fields=["name", "content", "owner", "creation"],
		order_by="creation asc",
	)
	communications = frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"communication_type": "Communication",
			"communication_medium": "Email",
		},
		fields=[
			"name",
			"subject",
			"content",
			"sender",
			"sender_full_name",
			"recipients",
			"cc",
			"bcc",
			"sent_or_received",
			"delivery_status",
			"creation",
			"owner",
		],
		order_by="creation asc",
	)
	return {"comments": comments, "communications": communications}


@frappe.whitelist()
def add_comment(reference_doctype: str, reference_name: str, content: str) -> dict:
	frappe.has_permission(reference_doctype, "read", doc=reference_name, throw=True)
	if not content or not content.strip():
		frappe.throw(frappe._("A comment needs some content."), exc=frappe.ValidationError)

	comment = frappe.new_doc("Comment")
	comment.update(
		{
			"comment_type": "Comment",
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"comment_email": frappe.session.user,
			"comment_by": frappe.utils.get_fullname(frappe.session.user),
			"content": content,
		}
	)
	comment.insert(ignore_permissions=True)
	return {"name": comment.name, "content": comment.content, "owner": comment.owner, "creation": comment.creation}


def _get_own_comment(reference_doctype: str, reference_name: str, comment_name: str):
	frappe.has_permission(reference_doctype, "read", doc=reference_name, throw=True)
	comment = frappe.get_doc("Comment", comment_name)
	if (
		comment.reference_doctype != reference_doctype
		or comment.reference_name != reference_name
		or comment.comment_type != "Comment"
	):
		frappe.throw(frappe._("That comment does not belong to this record."), exc=frappe.PermissionError)
	return comment


@frappe.whitelist()
def update_comment(reference_doctype: str, reference_name: str, comment_name: str, content: str) -> dict:
	comment = _get_own_comment(reference_doctype, reference_name, comment_name)
	# Same rule Frappe core's own Activity feed enforces for the "Edit" button (form_timeline.js,
	# setup_comment_actions) — the comment's own author, or an Administrator; deliberately not
	# gated on any doctype-level role, since a Comment's own permission list only grants System
	# Manager/Website Manager and would otherwise block any ordinary user editing their own words.
	if frappe.session.user not in ("Administrator", comment.owner):
		frappe.throw(frappe._("Only the comment's author can edit it."), exc=frappe.PermissionError)
	if not content or not content.strip():
		frappe.throw(frappe._("A comment needs some content."), exc=frappe.ValidationError)

	comment.content = content
	comment.save(ignore_permissions=True)
	return {"name": comment.name, "content": comment.content, "owner": comment.owner, "creation": comment.creation}


@frappe.whitelist()
def delete_comment(reference_doctype: str, reference_name: str, comment_name: str) -> None:
	comment = _get_own_comment(reference_doctype, reference_name, comment_name)
	# Same rule Frappe core's own Activity feed enforces for "Delete" (form_timeline.js,
	# setup_comment_actions): the comment's own author, or a System Manager.
	if frappe.session.user != comment.owner and "System Manager" not in frappe.get_roles():
		frappe.throw(frappe._("Only the comment's author or a System Manager can delete it."), exc=frappe.PermissionError)

	frappe.delete_doc("Comment", comment_name, ignore_permissions=True)
