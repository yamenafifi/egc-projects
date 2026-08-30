"""One Custom Field on core `Customer` — its fixed global identity (Client/Main Contractor/
Consultant/...), distinct from any role it plays on one particular project (that's
`EGC Project Stakeholder.role`, project-scoped). Every party this app deals with (client,
consultant, subcontractor, OEM, ...) is a plain `Customer` record now (no `EGC Organization`
doctype, no split by ERPNext's own accounting Party Type) — this field is the one piece of that
old doctype's own data core `Customer` has no equivalent for, so it's preserved here rather than
silently dropped.
"""

from __future__ import annotations

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

CUSTOM_FIELDS = {
	"Customer": [
		{
			"fieldname": "custom_organization_type",
			"label": "Organization Type",
			"fieldtype": "Select",
			# Leading blank line: an untouched Select must stay unset, never silently default to
			# the first option (frappe/model/create_new.py's `get_new_doc()` rule) — same
			# convention as `project_custom_fields.py`'s own Select fields.
			"options": (
				"\nClient\nMain Contractor\nConsultant\nArchitect\nOEM\nSubcontractor\n"
				"Specialty Contractor\nSupplier\nSpecialist Vendor\nOther"
			),
			"insert_after": "customer_name",
		},
	]
}


def create() -> None:
	create_custom_fields(CUSTOM_FIELDS, ignore_validate=True)
