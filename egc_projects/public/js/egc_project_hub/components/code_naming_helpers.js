// The code fields these dialogs preview (activity_code / document_number / submittal_number) are
// `read_only` — Discipline (+ Type) are the only things a person picks, the code itself is
// server-generated (code_naming.py's `assign_*_code`, called from each doctype's own
// `before_insert()`). This just shows that same live, so there's nothing to "protect" a
// hand-typed value from any more — always safe to overwrite.

export function apply_suggested_code(dialog, fieldname, suggestion) {
	dialog.set_value(fieldname, suggestion || "");
}
