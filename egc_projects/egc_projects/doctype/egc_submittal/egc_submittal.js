// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

frappe.ui.form.on("EGC Submittal", {
	refresh(frm) {
		frm.set_query("submittal_type", () => ({ filters: { enabled: 1 } }));
		frm.set_query("discipline", () => ({ filters: { enabled: 1 } }));
		frm.set_query("wbs_node", () => ({ filters: { project: frm.doc.project } }));

		if (!frm.is_new()) {
			render_submission_history(frm);
		}
	},
});

function render_submission_history(frm) {
	frappe.call({
		method: "egc_projects.egc_projects.doctype.egc_submittal.egc_submittal.get_submissions",
		args: { submittal: frm.doc.name },
		callback(r) {
			const rows = r.message || [];
			frm.__egc_submissions = rows;

			const field = frm.get_field("submission_history_html");
			if (field) {
				field.$wrapper.html(build_submission_history_html(rows));
			}
			update_new_submission_button(frm, rows);
		},
	});
}

function update_new_submission_button(frm, rows) {
	frm.clear_custom_buttons();

	const current = rows.find((row) => row.is_current);
	if (!current || current.submission_status !== "Responded") {
		return;
	}

	frm.add_custom_button(__("New Submission"), () => {
		frappe.call({
			method: "egc_projects.egc_projects.submittal_control.create_next_revision",
			args: { submittal: frm.doc.name },
			freeze: true,
			callback(r) {
				if (r.message) {
					frappe.set_route("Form", "EGC Submittal Revision", r.message);
				}
			},
		});
	}).addClass("btn-primary");
}

function build_submission_history_html(rows) {
	if (!rows || !rows.length) {
		return `<div class="text-muted">${__("No submissions yet.")}</div>`;
	}

	const body = rows
		.map((row) => {
			const current_badge = row.is_current
				? ` <span class="indicator-pill green">${__("Current")}</span>`
				: "";
			const link = `<a href="${frappe.utils.get_form_link("EGC Submittal Revision", row.name)}">${frappe.utils.escape_html(
				row.revision_label || ""
			)}</a>`;
			const docs = (row.documents || [])
				.map((d) => frappe.utils.escape_html(`${d.document_title || d.document || ""} (Rev ${d.revision || ""})`))
				.join("<br>");

			return `
				<tr>
					<td>${row.submission_seq}</td>
					<td>${link}${current_badge}</td>
					<td>${frappe.datetime.str_to_user(row.date_submitted) || ""}</td>
					<td>${frappe.datetime.str_to_user(row.due_date) || ""}</td>
					<td>${frappe.utils.escape_html(row.submission_status || "")}</td>
					<td>${frappe.utils.escape_html(row.response || "")}</td>
					<td>${frappe.datetime.str_to_user(row.response_date) || ""}</td>
					<td>${docs}</td>
				</tr>`;
		})
		.join("");

	return `
		<table class="table table-bordered table-sm">
			<thead>
				<tr>
					<th>${__("Seq")}</th>
					<th>${__("Label")}</th>
					<th>${__("Submitted")}</th>
					<th>${__("Due")}</th>
					<th>${__("Status")}</th>
					<th>${__("Response")}</th>
					<th>${__("Response Date")}</th>
					<th>${__("Documents")}</th>
				</tr>
			</thead>
			<tbody>${body}</tbody>
		</table>`;
}
