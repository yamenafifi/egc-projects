// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.ui.form.on("EGC Project Document", {
	refresh(frm) {
		frm.set_query("document_type", () => ({ filters: { enabled: 1 } }));
		frm.set_query("discipline", () => ({ filters: { enabled: 1 } }));
		frm.set_query("wbs_node", () => ({ filters: { project: frm.doc.project } }));

		if (!frm.is_new()) {
			frm.add_custom_button(__("New Revision"), () => new_revision(frm)).addClass("btn-primary");
			render_revision_history(frm);
		}
	},
});

function render_revision_history(frm) {
	frappe.call({
		method: "egc_projects.egc_projects.doctype.egc_project_document.egc_project_document.get_revisions",
		args: { document: frm.doc.name },
		callback(r) {
			frm.__egc_revisions = r.message || [];
			const field = frm.get_field("revision_history_html");
			if (field) {
				field.$wrapper.html(build_revision_table_html(frm.__egc_revisions));
			}
		},
	});
}

function build_revision_table_html(rows) {
	if (!rows || !rows.length) {
		return `<div class="text-muted">${__("No revisions yet.")}</div>`;
	}

	const body = rows
		.map((row) => {
			const file_link = row.file
				? `<a href="${frappe.utils.escape_html(row.file)}" target="_blank">${__("Open")}</a>`
				: "";
			const current_badge = row.is_current
				? ` <span class="indicator-pill green">${__("Current")}</span>`
				: "";
			return `
				<tr>
					<td>${row.revision_seq}</td>
					<td>${frappe.utils.escape_html(row.revision || "")}${current_badge}</td>
					<td>${frappe.utils.escape_html(row.revision_status || "")}</td>
					<td>${frappe.datetime.str_to_user(row.revision_date) || ""}</td>
					<td>${frappe.datetime.str_to_user(row.issue_date) || ""}</td>
					<td>${file_link}</td>
					<td>${frappe.utils.escape_html(row.remarks || "")}</td>
				</tr>`;
		})
		.join("");

	return `
		<table class="table table-bordered table-sm">
			<thead>
				<tr>
					<th>${__("Seq")}</th>
					<th>${__("Revision")}</th>
					<th>${__("Status")}</th>
					<th>${__("Revision Date")}</th>
					<th>${__("Issue Date")}</th>
					<th>${__("File")}</th>
					<th>${__("Remarks")}</th>
				</tr>
			</thead>
			<tbody>${body}</tbody>
		</table>`;
}

function suggest_next_revision(rows) {
	if (!rows || !rows.length) {
		return "00";
	}
	// rows are newest-first; a purely numeric label suggests the next zero-padded number,
	// otherwise leave it blank for the user to fill in (labels like "A"/"B" aren't ours to guess).
	const latest = rows[0].revision || "";
	if (/^\d+$/.test(latest)) {
		return String(Number(latest) + 1).padStart(latest.length, "0");
	}
	return "";
}

function new_revision(frm) {
	const open_with = (rows) => {
		frappe.new_doc("EGC Project Document Revision", {
			document: frm.doc.name,
			project: frm.doc.project,
			revision: suggest_next_revision(rows),
		});
	};

	if (frm.__egc_revisions) {
		open_with(frm.__egc_revisions);
		return;
	}

	frappe.call({
		method: "egc_projects.egc_projects.doctype.egc_project_document.egc_project_document.get_revisions",
		args: { document: frm.doc.name },
		callback(r) {
			open_with(r.message || []);
		},
	});
}
