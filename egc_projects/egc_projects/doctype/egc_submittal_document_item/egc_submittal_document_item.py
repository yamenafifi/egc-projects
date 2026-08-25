# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class EGCSubmittalDocumentItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		document: DF.Link | None
		document_revision: DF.Link
		document_title: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		revision: DF.Data | None
	# end: auto-generated types
