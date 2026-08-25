// Copyright (c) 2026, EGC and contributors
// For license information, please see license.txt

// Kept in sync by hand with constants.ACTIVITY_CLOSED_STATUSES — see egc_activity.js.
const EGC_ACTIVITY_CLOSED_STATUSES = ["Completed", "Cancelled"];

const EGC_ACTIVITY_STATUS_COLORS = {
	"Not Started": "grey",
	"In Progress": "blue",
	"On Hold": "orange",
	Completed: "green",
	Cancelled: "dark grey",
};

frappe.listview_settings["EGC Activity"] = {
	add_fields: ["status", "planned_end_date"],

	get_indicator(doc) {
		if (
			!EGC_ACTIVITY_CLOSED_STATUSES.includes(doc.status) &&
			doc.planned_end_date &&
			doc.planned_end_date < frappe.datetime.get_today()
		) {
			return [__("Overdue"), "red", "status,not in,Completed,Cancelled"];
		}

		return [
			__(doc.status),
			EGC_ACTIVITY_STATUS_COLORS[doc.status] || "grey",
			"status,=," + doc.status,
		];
	},

	onload(listview) {
		// A derived-overdue shortcut: no field is stored for it, so this composes the same two
		// conditions used by is_overdue() at click time rather than filtering on a real column.
		listview.page.add_inner_button(__("Overdue"), () => {
			listview.filter_area.clear();
			listview.filter_area.add([
				[listview.doctype, "status", "not in", ["Completed", "Cancelled"]],
				[listview.doctype, "planned_end_date", "<", frappe.datetime.get_today()],
			]);
		});
	},
};
