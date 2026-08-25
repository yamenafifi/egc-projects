"""Single definition of every status enum and shared magic value in EGC Projects.

Anything that appears in a DocType `Select` option list and is also referenced from Python
belongs here, so a label change is a one-file change. Import from here; never re-type a
literal status string in a controller, report or API method.
"""

# --- EGC Activity -----------------------------------------------------------------

ACTIVITY_NOT_STARTED = "Not Started"
ACTIVITY_IN_PROGRESS = "In Progress"
ACTIVITY_ON_HOLD = "On Hold"
ACTIVITY_COMPLETED = "Completed"
ACTIVITY_CANCELLED = "Cancelled"

ACTIVITY_STATUSES = (
	ACTIVITY_NOT_STARTED,
	ACTIVITY_IN_PROGRESS,
	ACTIVITY_ON_HOLD,
	ACTIVITY_COMPLETED,
	ACTIVITY_CANCELLED,
)

#: Statuses for which a past planned finish date does *not* count as overdue.
ACTIVITY_CLOSED_STATUSES = (ACTIVITY_COMPLETED, ACTIVITY_CANCELLED)

# --- EGC WBS Node -----------------------------------------------------------------

WBS_ACTIVE = "Active"
WBS_ON_HOLD = "On Hold"
WBS_COMPLETED = "Completed"
WBS_CANCELLED = "Cancelled"

WBS_STATUSES = (WBS_ACTIVE, WBS_ON_HOLD, WBS_COMPLETED, WBS_CANCELLED)

# --- EGC Project Document Revision ------------------------------------------------

REVISION_DRAFT = "Draft"
REVISION_ISSUED = "Issued"
REVISION_SUPERSEDED = "Superseded"
REVISION_CANCELLED = "Cancelled"

REVISION_STATUSES = (REVISION_DRAFT, REVISION_ISSUED, REVISION_SUPERSEDED, REVISION_CANCELLED)

# --- EGC Project Document (derived) -----------------------------------------------

DOCUMENT_NO_REVISION = "No Revision"
DOCUMENT_DRAFT = "Draft"
DOCUMENT_ISSUED = "Issued"
DOCUMENT_CANCELLED = "Cancelled"

DOCUMENT_STATUSES = (
	DOCUMENT_NO_REVISION,
	DOCUMENT_DRAFT,
	DOCUMENT_ISSUED,
	DOCUMENT_CANCELLED,
)

# --- Review responses (shared by Submittal + Document approval display) -----------

RESPONSE_APPROVED = "Approved"
RESPONSE_APPROVED_WITH_COMMENTS = "Approved with Comments"
RESPONSE_REVISE_AND_RESUBMIT = "Revise & Resubmit"
RESPONSE_REJECTED = "Rejected"

REVIEW_RESPONSES = (
	RESPONSE_APPROVED,
	RESPONSE_APPROVED_WITH_COMMENTS,
	RESPONSE_REVISE_AND_RESUBMIT,
	RESPONSE_REJECTED,
)

# --- EGC Project Document.approval_status (derived from the CURRENT revision only) --

APPROVAL_NOT_SUBMITTED = "Not Submitted"
APPROVAL_UNDER_REVIEW = "Under Review"

DOCUMENT_APPROVAL_STATUSES = (APPROVAL_NOT_SUBMITTED, APPROVAL_UNDER_REVIEW, *REVIEW_RESPONSES)

# --- EGC Submittal Revision --------------------------------------------------------

SUBMISSION_DRAFT = "Draft"
SUBMISSION_SUBMITTED = "Submitted"
SUBMISSION_UNDER_REVIEW = "Under Review"
SUBMISSION_RESPONDED = "Responded"
SUBMISSION_CANCELLED = "Cancelled"

SUBMISSION_STATUSES = (
	SUBMISSION_DRAFT,
	SUBMISSION_SUBMITTED,
	SUBMISSION_UNDER_REVIEW,
	SUBMISSION_RESPONDED,
	SUBMISSION_CANCELLED,
)

#: Submissions still awaiting a reviewer response.
SUBMISSION_OPEN_STATUSES = (SUBMISSION_SUBMITTED, SUBMISSION_UNDER_REVIEW)

# --- EGC Submittal (derived) --------------------------------------------------------

SUBMITTAL_STATUSES = (
	SUBMISSION_DRAFT,
	SUBMISSION_SUBMITTED,
	SUBMISSION_UNDER_REVIEW,
	*REVIEW_RESPONSES,
)

# --- Relationship layer -------------------------------------------------------------

LINK_PURPOSE_REFERENCE = "Reference"
LINK_PURPOSE_REQUIREMENT = "Requirement"

LINK_PURPOSES = (LINK_PURPOSE_REFERENCE, LINK_PURPOSE_REQUIREMENT)

# --- Roles ---------------------------------------------------------------------------

ROLE_PROJECT_MANAGER = "EGC Project Manager"
ROLE_PROJECT_ENGINEER = "EGC Project Engineer"
ROLE_DOCUMENT_CONTROLLER = "EGC Document Controller"
ROLE_PROJECT_VIEWER = "EGC Project Viewer"

EGC_ROLES = (
	ROLE_PROJECT_MANAGER,
	ROLE_PROJECT_ENGINEER,
	ROLE_DOCUMENT_CONTROLLER,
	ROLE_PROJECT_VIEWER,
)

#: Roles allowed to read ERPNext project financial actuals through the Project Hub.
FINANCIAL_ROLES = (
	ROLE_PROJECT_MANAGER,
	"Projects Manager",
	"Accounts User",
	"Accounts Manager",
	"System Manager",
)
