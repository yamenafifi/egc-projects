// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.ui.form.on("EGC Project Document Revision", {
	refresh(frm) {
		frm.set_query("document", () => {
			if (frm.doc.project) {
				return { filters: { project: frm.doc.project } };
			}
			return {};
		});

		if (frm.doc.docstatus === 0) {
			frm.set_intro(
				__(
					"Submitting this revision issues it permanently: the file can never be replaced afterwards, and any previously current revision of this document becomes Superseded. Only Draft revisions can be deleted."
				),
				"orange"
			);
		} else {
			frm.set_intro("");
		}

		set_attachment_folder(frm);
	},
	document(frm) {
		set_attachment_folder(frm);
	},
});

// Native-form parity with the Hub's own "New Revision" dialog — routes the upload into
// Home/Projects/<project>/Drawings vs .../Documents instead of the default Home/Attachments
// bucket (see project_files.py). Neither `is_drawing` nor the project's Drawings/Documents split
// is preloaded on this raw form, so it's a small chained lookup instead of the single already
// -loaded field the Hub dialog gets to reuse.
function set_attachment_folder(frm) {
	if (!frm.doc.project || !frm.doc.document) return;
	frappe.db.get_value("EGC Project Document", frm.doc.document, "document_type").then(({ message }) => {
		if (!message || !message.document_type) return;
		frappe.db.get_value("EGC Document Type", message.document_type, "is_drawing").then(({ message: type_info }) => {
			const is_drawing = type_info && Number(type_info.is_drawing);
			const folder = `Home/Projects/${frm.doc.project}/${is_drawing ? "Drawings" : "Documents"}`;
			for (const fieldname of ["file", "native_file"]) {
				if (frm.fields_dict[fieldname]) frm.set_df_property(fieldname, "options", { folder });
			}
		});
	});
}
