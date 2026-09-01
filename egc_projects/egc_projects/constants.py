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


# --- EGC Project Document Revision ------------------------------------------------

REVISION_DRAFT = "Draft"
REVISION_ISSUED = "Issued"
REVISION_SUPERSEDED = "Superseded"
REVISION_CANCELLED = "Cancelled"

# --- EGC Project Document (derived) -----------------------------------------------

DOCUMENT_NO_REVISION = "No Revision"
DOCUMENT_DRAFT = "Draft"
DOCUMENT_ISSUED = "Issued"
DOCUMENT_CANCELLED = "Cancelled"

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

# --- EGC Submittal Revision --------------------------------------------------------

SUBMISSION_DRAFT = "Draft"
SUBMISSION_SUBMITTED = "Submitted"
SUBMISSION_UNDER_REVIEW = "Under Review"
SUBMISSION_RESPONDED = "Responded"
SUBMISSION_CANCELLED = "Cancelled"

#: Submissions still awaiting a reviewer response.
SUBMISSION_OPEN_STATUSES = (SUBMISSION_SUBMITTED, SUBMISSION_UNDER_REVIEW)

# --- Relationship layer -------------------------------------------------------------

LINK_PURPOSE_REFERENCE = "Reference"
LINK_PURPOSE_REQUIREMENT = "Requirement"

LINK_PURPOSES = (LINK_PURPOSE_REFERENCE, LINK_PURPOSE_REQUIREMENT)

# --- Roles ---------------------------------------------------------------------------

ROLE_PROJECT_MANAGER = "EGC Project Manager"
ROLE_PROJECT_ENGINEER = "EGC Project Engineer"
ROLE_DOCUMENT_CONTROLLER = "EGC Document Controller"
ROLE_PROJECT_VIEWER = "EGC Project Viewer"
#: For an external party (Main Contractor, Client, Consultant, ...) given their own login —
#: always paired with a User Permission scoping them to the one Project they're allowed to see
#: (docs/ARCHITECTURE_V2.md's external-access design). Same read-only doctype footprint as
#: ROLE_PROJECT_VIEWER, kept as a genuinely separate role rather than reusing it: an external
#: account's access surface needs to stay independently auditable and must never silently widen
#: just because ROLE_PROJECT_VIEWER (an internal-staff role) gains some new capability later.
#: Deliberately absent from every financial doctype's permissions (EGC Change Order) and from
#: FINANCIAL_ROLES below — an external party never sees commercial figures through this role.
#: This is ALSO the role a client-side submittal REVIEWER holds — not a separate one. Recording
#: a response on a Submittal Review Step (`record_step_response`, submittal_control.py) is
#: authorized by identity ("are you the assigned reviewer_user"), not by doctype role
#: permission, so this read-only role is already sufficient for the write itself; no broader
#: write grant was needed (confirmed by reading that function before assuming otherwise).
ROLE_EXTERNAL_VIEWER = "EGC External Viewer"

EGC_ROLES = (
	ROLE_PROJECT_MANAGER,
	ROLE_PROJECT_ENGINEER,
	ROLE_DOCUMENT_CONTROLLER,
	ROLE_PROJECT_VIEWER,
	ROLE_EXTERNAL_VIEWER,
)

#: Roles allowed to read ERPNext project financial actuals through the Project Hub.
FINANCIAL_ROLES = (
	ROLE_PROJECT_MANAGER,
	"Projects Manager",
	"Accounts User",
	"Accounts Manager",
	"System Manager",
)

#: Holders of any of these roles see EVERY project, full stop — `grant_portal_access`
#: (api/directory.py) never scopes them with a `Project` User Permission, because Frappe's own
#: User Permission enforcement has no role-based bypass at all (confirmed against
#: frappe/permissions.py): the moment a user has even ONE User Permission row for
#: `allow="Project"`, they can see only the allowed value(s), regardless of what roles they hold.
#: Direct user instruction, following a real regression: adding themselves (System Manager) to a
#: project's Directory and granting access silently cost them visibility of every OTHER project.
PROJECT_VISIBILITY_BYPASS_ROLES = ("System Manager", "Projects Manager")
# --- v2: Submittal Review Steps -----------------------------------------------------------

STEP_PENDING = "Pending"
STEP_IN_REVIEW = "In Review"
STEP_RESPONDED = "Responded"
STEP_SKIPPED = "Skipped"

# --- v2: Activity Dependencies -------------------------------------------------------------

DEPENDENCY_FS = "Finish-to-Start"
DEPENDENCY_SS = "Start-to-Start"
DEPENDENCY_FF = "Finish-to-Finish"
DEPENDENCY_SF = "Start-to-Finish"

# --- v2: Project Profile ---------------------------------------------------------------------
#
# Also the source of the literal Select `options` strings in `project_custom_fields.py`
# (`custom_egc_project_stage`/`sector`/`delivery_method`/`contract_type`) — those used to hand-
# type an independent copy of these same four lists, which is exactly the mistake this module's
# own docstring warns against ("never re-type a literal status string").

PROJECT_STAGES = ("Design", "Procurement", "Construction", "Commissioning", "Closeout", "Warranty")
SECTORS = ("Healthcare", "Industrial", "Commercial", "Infrastructure", "Other")
DELIVERY_METHODS = ("Design-Bid-Build", "Design-Build", "EPC", "Turnkey", "Other")
CONTRACT_TYPES = ("Lump Sum", "Unit Price", "Cost Plus", "Time & Material", "Other")
