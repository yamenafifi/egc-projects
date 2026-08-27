"""Comments on any EGC record — Level 0 §7/§32: an external reviewer must be able to add
response comments, the same as any internal user. A thin, explicit wrapper around Frappe's own
`Comment` doctype and `frappe.desk.form.utils.add_comment` rather than a new comment system —
this module exists only because `add_comment` has no whitelisted counterpart for LISTING a
document's comments, and because listing them for an arbitrary reference doctype needs the same
explicit "can you even read this record" gate `add_comment` itself already applies.

Generic by reference_doctype/reference_name, not tied to Submittals specifically — reusable for
Documents, Activities, and future RFIs/Inspections without a new module per record type.
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
