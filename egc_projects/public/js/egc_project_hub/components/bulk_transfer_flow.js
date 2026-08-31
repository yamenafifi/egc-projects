// Export/Import, shared by every register that has it (WbsTab.vue, ActivitiesTab.vue,
// SubmittalsTab.vue, DocumentsTab.vue) — direct user instruction: mirror ERPNext's own Export
// Data / Import Data modules, but as buttons that stay INSIDE the Project Hub, never a
// navigate-away to Frappe's native `/app/data-export`/`/app/data-import` list views.
//
// Both dialogs are thin shells around api/bulk_transfer.py, which does the real work by calling
// straight into Frappe's own Data Export/Data Import machinery — this file only ever collects
// the handful of options that machinery needs (file type, whether to include current data,
// insert-vs-update, and "Send Email") and hands them off.

import { download_export_template, import_records } from "./bulk_transfer_api";

/**
 * @param {Object} opts
 * @param {string} opts.project
 * @param {string} opts.doctype - e.g. "EGC Activity"
 * @param {string} opts.label - plain-language name for dialog titles, e.g. "Activities"
 */
export function openExportDialog({ project, doctype, label }) {
	const dialog = new frappe.ui.Dialog({
		title: __("Export {0}", [label]),
		fields: [
			{
				fieldname: "with_data",
				fieldtype: "Select",
				label: __("What to download"),
				options: [
					{ label: __("This project's current records"), value: "1" },
					{ label: __("A blank template only"), value: "0" },
				],
				default: "1",
				reqd: 1,
			},
			{
				fieldname: "file_type",
				fieldtype: "Select",
				label: __("File Type"),
				options: ["Excel", "CSV"],
				default: "Excel",
				reqd: 1,
			},
		],
		primary_action_label: __("Download"),
		primary_action(values) {
			// A real file download, not a frappe.call() — see bulk_transfer_api.js's own
			// docstring for why. Nothing to await: the browser's own save flow takes over from
			// here, so the dialog just closes immediately.
			download_export_template(project, doctype, values.file_type, values.with_data === "1");
			dialog.hide();
		},
	});
	dialog.show();
}

/**
 * @param {Object} opts
 * @param {string} opts.project
 * @param {string} opts.doctype
 * @param {string} opts.label
 * @param {() => void} [opts.onImported] - called once the import finishes (even partially), so
 *   the caller can reload its own register.
 */
export function openImportDialog({ project, doctype, label, onImported }) {
	const dialog = new frappe.ui.Dialog({
		title: __("Import {0}", [label]),
		fields: [
			{
				fieldname: "file_url",
				fieldtype: "Attach",
				label: __("File"),
				description: __(
					"Use the Export dialog's own template if you don't already have one — the column headers must match it."
				),
				reqd: 1,
			},
			{
				fieldname: "update_existing",
				fieldtype: "Check",
				label: __("Update existing records"),
				description: __(
					"Leave unchecked to insert new records. Check this only when your file's rows reference records that already exist (by their own ID column)."
				),
			},
			{
				fieldname: "send_email",
				fieldtype: "Check",
				label: __("Send Email"),
				description: __(
					"Off by default for a bulk import, same as Frappe's own Data Import tool — turn this on only if you actually want every notification a normal, one-at-a-time creation would send (e.g. a Submittal Manager's task) to go out for every imported row."
				),
			},
		],
		primary_action_label: __("Start Import"),
		async primary_action(values) {
			dialog.disable_primary_action();
			try {
				const result = await import_records(
					project,
					doctype,
					values.file_url,
					values.update_existing,
					values.send_email
				);
				dialog.hide();
				onImported && onImported();

				const failures = (result.log || []).filter((row) => !row.success);
				if (!result.failure_count) {
					frappe.msgprint({
						title: __("Import Complete"),
						message: __("{0} record(s) imported successfully.", [result.success_count]),
						indicator: "green",
					});
				} else {
					const failure_lines = failures
						.slice(0, 10)
						.map((row) => `<li>${frappe.utils.escape_html(row.exception || __("Failed"))}</li>`)
						.join("");
					frappe.msgprint({
						title: __("Import Finished With Errors"),
						message: __("{0} succeeded, {1} failed:", [result.success_count, result.failure_count]) + `<ul>${failure_lines}</ul>`,
						indicator: "orange",
					});
				}
			} catch (e) {
				dialog.enable_primary_action();
				frappe.msgprint({ title: __("Could Not Import"), message: e.message, indicator: "red" });
			}
		},
	});
	dialog.show();
}
