frappe.listview_settings["EGC WBS Node"] = {
	get_indicator: function (doc) {
		var status_colors = {
			Active: "green",
			"On Hold": "orange",
			Completed: "blue",
			Cancelled: "red",
		};
		return [__(doc.status), status_colors[doc.status] || "grey", "status,=," + doc.status];
	},
};
