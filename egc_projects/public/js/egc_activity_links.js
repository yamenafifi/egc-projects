// Shared client renderer for the `EGC Activity Link` relationship layer (docs/ARCHITECTURE.md
// §2.6). Two reusable entry points are exposed on the `egc_projects` namespace:
//
//   egc_projects.render_activity_links(frm, wrapper_field)
//       "Linked Documents & Submittals" — for the EGC Activity form.
//   egc_projects.render_related_activities(frm, wrapper_field)
//       "Related Activities" — for the EGC Project Document / EGC Submittal form.
//
// Both are wired up below via `frappe.ui.form.on`, declared in this file only. This composes
// with whatever the Activity/Document/Submittal doctype-owned scripts register for the same
// doctype — Frappe supports multiple `on` registrations per doctype — so this file never touches
// egc_activity.js / egc_project_document.js / egc_submittal.js, and never adds an HTML field to
// their DocType JSON. The section is injected at runtime via `frm.dashboard.add_section()`.
//
// `EGC Submittal` may not exist yet (built concurrently by another work package); every call
// that touches it is guarded by `frappe.db.exists("DocType", ...)` so this degrades gracefully.

import { LINK_PURPOSES } from "./shared_constants";

frappe.provide("egc_projects");

(function () {
	"use strict";

	// Mirrors `egc_projects.egc_projects.relationships.ALLOWED_LINK_DOCTYPES`. The server
	// (`EGC Activity Link.validate`) is the actual enforcement — this list only drives which
	// options the "Add Link" dialog offers; keep it in sync by hand when the registry changes.
	const ALLOWED_LINK_DOCTYPES = {
		"EGC Project Document": { label: __("Project Document") },
		"EGC Submittal": { label: __("Submittal") },
	};

	const METHODS = {
		get_links_for_activity: "egc_projects.egc_projects.relationships.get_links_for_activity",
		get_activities_for: "egc_projects.egc_projects.relationships.get_activities_for",
		add_link: "egc_projects.egc_projects.relationships.add_link",
		remove_link: "egc_projects.egc_projects.relationships.remove_link",
	};

	function doctype_exists(doctype) {
		return frappe.db.exists("DocType", doctype).then((exists) => !!exists);
	}

	function available_link_doctypes() {
		const names = Object.keys(ALLOWED_LINK_DOCTYPES);
		return Promise.all(names.map((name) => doctype_exists(name).then((exists) => (exists ? name : null)))).then(
			(results) => results.filter(Boolean)
		);
	}

	function open_form(doctype, name) {
		frappe.set_route("Form", doctype, name);
	}

	function confirm_remove(on_confirmed) {
		frappe.confirm(__("Remove this link?"), on_confirmed);
	}

	function remove_link(name, on_done) {
		frappe.call({
			method: METHODS.remove_link,
			args: { name },
			freeze: true,
		}).then(() => on_done());
	}

	// Every relationship section lives in its own cached dashboard body, keyed by `wrapper_field`
	// so repeated `refresh` calls re-render in place instead of stacking a new section each time.
	function get_or_create_section(frm, wrapper_field, label) {
		frm.__egc_relationship_sections = frm.__egc_relationship_sections || {};
		if (!frm.__egc_relationship_sections[wrapper_field]) {
			frm.__egc_relationship_sections[wrapper_field] = frm.dashboard.add_section("", label);
		}
		return frm.__egc_relationship_sections[wrapper_field];
	}

	function loading_html() {
		return `<div class="text-muted small egc-relationship-loading">${__("Loading...")}</div>`;
	}

	function empty_html(message) {
		return `<div class="text-muted small">${frappe.utils.escape_html(message)}</div>`;
	}

	// -- "Linked Documents & Submittals" on the EGC Activity form ------------------------------

	egc_projects.render_activity_links = function (frm, wrapper_field) {
		if (!frm.doc || frm.is_new()) return;

		const section = get_or_create_section(frm, wrapper_field, __("Linked Documents & Submittals"));
		section.html(loading_html());

		frappe.call({
			method: METHODS.get_links_for_activity,
			args: { activity: frm.doc.name },
		}).then((r) => {
			render_activity_links_table(frm, wrapper_field, section, r.message || []);
		});
	};

	function render_activity_links_table(frm, wrapper_field, section, rows) {
		const $wrapper = $(`
			<div class="egc-activity-links">
				<div class="egc-relationship-toolbar" style="margin-bottom: 8px;"></div>
				<div class="egc-relationship-table"></div>
			</div>
		`);
		section.empty().append($wrapper);

		$(`<button type="button" class="btn btn-xs btn-default">${__("Add Link")}</button>`)
			.appendTo($wrapper.find(".egc-relationship-toolbar"))
			.on("click", () => show_add_link_dialog(frm, wrapper_field));

		const $table_wrapper = $wrapper.find(".egc-relationship-table");
		if (!rows.length) {
			$table_wrapper.append(empty_html(__("No linked documents or submittals yet.")));
			return;
		}

		const $table = $(`
			<table class="table table-bordered egc-relationship-table-inner" style="margin-top: 4px;">
				<thead>
					<tr>
						<th>${__("Type")}</th>
						<th>${__("Number / Title")}</th>
						<th>${__("Current")}</th>
						<th>${__("Status")}</th>
						<th>${__("Purpose")}</th>
						<th></th>
					</tr>
				</thead>
				<tbody></tbody>
			</table>
		`);
		const $tbody = $table.find("tbody");

		rows.forEach((row) => {
			const number = row.document_number || row.submittal_number || "";
			const current = row.current_revision_label || row.current_submission_label || "";
			const status = row.approval_status || row.submittal_status || "";
			const type_label = (ALLOWED_LINK_DOCTYPES[row.link_doctype] || {}).label || row.link_doctype;
			const title = number ? `${number} — ${row.link_title || ""}` : row.link_title || row.link_name;

			const $tr = $(`
				<tr>
					<td>${frappe.utils.escape_html(type_label)}</td>
					<td><a href="#" class="egc-link-open">${frappe.utils.escape_html(title)}</a></td>
					<td>${frappe.utils.escape_html(current)}</td>
					<td>${frappe.utils.escape_html(status)}</td>
					<td>${frappe.utils.escape_html(row.link_purpose || "")}</td>
					<td class="text-right">
						<button type="button" class="btn btn-xs btn-default egc-link-remove">${__("Remove")}</button>
					</td>
				</tr>
			`);
			$tr.find(".egc-link-open").on("click", (e) => {
				e.preventDefault();
				open_form(row.link_doctype, row.link_name);
			});
			$tr.find(".egc-link-remove").on("click", () => {
				confirm_remove(() =>
					remove_link(row.name, () => egc_projects.render_activity_links(frm, wrapper_field))
				);
			});
			$tbody.append($tr);
		});

		$table_wrapper.append($table);
	}

	function show_add_link_dialog(frm, wrapper_field) {
		available_link_doctypes().then((doctypes) => {
			if (!doctypes.length) {
				frappe.msgprint(__("No linkable record types are available yet."));
				return;
			}

			const dialog = new frappe.ui.Dialog({
				title: __("Add Link"),
				fields: [
					{
						fieldname: "link_doctype",
						fieldtype: "Select",
						label: __("Link Type"),
						options: doctypes,
						default: doctypes[0],
						reqd: 1,
					},
					{
						fieldname: "link_name",
						fieldtype: "Dynamic Link",
						label: __("Record"),
						options: "link_doctype",
						reqd: 1,
						get_query: () => ({ filters: { project: frm.doc.project } }),
					},
					{
						fieldname: "link_purpose",
						fieldtype: "Select",
						label: __("Purpose"),
						options: LINK_PURPOSES,
						default: LINK_PURPOSES[0],
					},
					{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
				],
				primary_action_label: __("Add"),
				primary_action(values) {
					frappe.call({
						method: METHODS.add_link,
						args: {
							activity: frm.doc.name,
							link_doctype: values.link_doctype,
							link_name: values.link_name,
							link_purpose: values.link_purpose,
							remarks: values.remarks,
						},
						freeze: true,
					}).then(() => {
						dialog.hide();
						egc_projects.render_activity_links(frm, wrapper_field);
					});
				},
			});
			dialog.show();
		});
	}

	// -- "Related Activities" on the EGC Project Document / EGC Submittal form -----------------

	egc_projects.render_related_activities = function (frm, wrapper_field) {
		if (!frm.doc || frm.is_new()) return;

		const section = get_or_create_section(frm, wrapper_field, __("Related Activities"));
		section.html(loading_html());

		frappe.call({
			method: METHODS.get_activities_for,
			args: { link_doctype: frm.doctype, link_name: frm.doc.name },
		}).then((r) => {
			render_related_activities_table(frm, wrapper_field, section, r.message || []);
		});
	};

	function render_related_activities_table(frm, wrapper_field, section, rows) {
		const $wrapper = $(`
			<div class="egc-related-activities">
				<div class="egc-relationship-toolbar" style="margin-bottom: 8px;"></div>
				<div class="egc-relationship-table"></div>
			</div>
		`);
		section.empty().append($wrapper);

		$(`<button type="button" class="btn btn-xs btn-default">${__("Add Activity Link")}</button>`)
			.appendTo($wrapper.find(".egc-relationship-toolbar"))
			.on("click", () => show_add_activity_dialog(frm, wrapper_field));

		const $table_wrapper = $wrapper.find(".egc-relationship-table");
		if (!rows.length) {
			$table_wrapper.append(empty_html(__("No activities are linked to this record yet.")));
			return;
		}

		const $table = $(`
			<table class="table table-bordered egc-relationship-table-inner" style="margin-top: 4px;">
				<thead>
					<tr>
						<th>${__("Activity")}</th>
						<th>${__("Status")}</th>
						<th>${__("Purpose")}</th>
						<th></th>
					</tr>
				</thead>
				<tbody></tbody>
			</table>
		`);
		const $tbody = $table.find("tbody");

		rows.forEach((row) => {
			const title = `${row.activity_code} — ${row.activity_name}`;
			const $tr = $(`
				<tr>
					<td><a href="#" class="egc-activity-open">${frappe.utils.escape_html(title)}</a></td>
					<td>${frappe.utils.escape_html(row.status || "")}</td>
					<td>${frappe.utils.escape_html(row.link_purpose || "")}</td>
					<td class="text-right">
						<button type="button" class="btn btn-xs btn-default egc-link-remove">${__("Remove")}</button>
					</td>
				</tr>
			`);
			$tr.find(".egc-activity-open").on("click", (e) => {
				e.preventDefault();
				open_form("EGC Activity", row.activity);
			});
			$tr.find(".egc-link-remove").on("click", () => {
				confirm_remove(() =>
					remove_link(row.name, () => egc_projects.render_related_activities(frm, wrapper_field))
				);
			});
			$tbody.append($tr);
		});

		$table_wrapper.append($table);
	}

	function show_add_activity_dialog(frm, wrapper_field) {
		const dialog = new frappe.ui.Dialog({
			title: __("Add Activity Link"),
			fields: [
				{
					fieldname: "activity",
					fieldtype: "Link",
					label: __("Activity"),
					options: "EGC Activity",
					reqd: 1,
					get_query: () => ({ filters: { project: frm.doc.project } }),
				},
				{
					fieldname: "link_purpose",
					fieldtype: "Select",
					label: __("Purpose"),
					options: LINK_PURPOSES,
					default: LINK_PURPOSES[0],
				},
				{ fieldname: "remarks", fieldtype: "Small Text", label: __("Remarks") },
			],
			primary_action_label: __("Add"),
			primary_action(values) {
				frappe.call({
					method: METHODS.add_link,
					args: {
						activity: values.activity,
						link_doctype: frm.doctype,
						link_name: frm.doc.name,
						link_purpose: values.link_purpose,
						remarks: values.remarks,
					},
					freeze: true,
				}).then(() => {
					dialog.hide();
					egc_projects.render_related_activities(frm, wrapper_field);
				});
			},
		});
		dialog.show();
	}

	// -- Wiring: declared here only, never inside the doctype-owned scripts --------------------

	frappe.ui.form.on("EGC Activity", {
		refresh(frm) {
			egc_projects.render_activity_links(frm, "egc_activity_links_section");
		},
	});

	frappe.ui.form.on("EGC Project Document", {
		refresh(frm) {
			egc_projects.render_related_activities(frm, "egc_related_activities_section");
		},
	});

	// `EGC Submittal` may not exist yet on this site; the handler is harmless to register and
	// simply never fires until that work package's DocType lands.
	frappe.ui.form.on("EGC Submittal", {
		refresh(frm) {
			egc_projects.render_related_activities(frm, "egc_related_activities_section");
		},
	});
})();
