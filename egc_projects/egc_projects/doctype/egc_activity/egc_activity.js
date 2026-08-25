// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

// Kept in sync by hand with constants.ACTIVITY_CLOSED_STATUSES — client-side is UX only, the
// server-side truth lives in egc_activity.py / constants.py (docs/ARCHITECTURE.md §0.5).
const EGC_ACTIVITY_CLOSED_STATUSES = ["Completed", "Cancelled"];

frappe.ui.form.on("EGC Activity", {
	setup(frm) {
		frm.set_query("parent_egc_activity", () => ({
			filters: {
				project: frm.doc.project,
				is_group: 1,
				name: ["!=", frm.doc.name],
			},
		}));

		frm.set_query("wbs_node", () => ({
			filters: {
				project: frm.doc.project,
			},
		}));

		frm.set_query("discipline", () => ({
			filters: {
				enabled: 1,
			},
		}));
	},

	refresh(frm) {
		frm.trigger("show_overdue_indicator");

		if (!frm.is_new() && frm.doc.project) {
			frm.add_custom_button(__("View Tree"), () => {
				frappe.set_route("Tree", "EGC Activity", { project: frm.doc.project });
			});
		}
	},

	show_overdue_indicator(frm) {
		if (frm.is_new() || !frm.doc.planned_end_date) return;
		if (EGC_ACTIVITY_CLOSED_STATUSES.includes(frm.doc.status)) return;

		const overdue =
			frappe.datetime.get_diff(frm.doc.planned_end_date, frappe.datetime.get_today()) < 0;
		if (overdue) {
			frm.page.set_indicator(__("Overdue"), "red");
		}
	},

	status(frm) {
		frm.trigger("show_overdue_indicator");
	},

	planned_end_date(frm) {
		frm.trigger("show_overdue_indicator");
	},
});
