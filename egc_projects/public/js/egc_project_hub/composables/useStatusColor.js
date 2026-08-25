// One status -> indicator-pill colour map, shared by every tab, so "Approved" is always the
// same green whether it came from a Submittal, a Document approval_status or a Revision.

const COLOR_MAP = {
	// Activity / WBS
	"Not Started": "gray",
	"In Progress": "blue",
	Active: "blue",
	"On Hold": "orange",
	Completed: "green",
	Cancelled: "gray",

	// Document / Revision
	"No Revision": "gray",
	Draft: "gray",
	Issued: "green",
	Superseded: "darkgrey",

	// Submittal / approval response
	Submitted: "orange",
	"Under Review": "orange",
	Responded: "blue",
	"Not Submitted": "gray",
	Approved: "green",
	"Approved with Comments": "blue",
	"Revise & Resubmit": "red",
	Rejected: "red",
};

export function statusColor(status) {
	return COLOR_MAP[status] || "gray";
}

export const OVERDUE_COLOR = "red";
