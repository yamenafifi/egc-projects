app_name = "egc_projects"
app_title = "EGC Projects"
app_publisher = "EGC"
app_description = (
	"Construction project management for EGC: WBS, Activities, controlled Documents, "
	"Drawing Register and Submittals on top of ERPNext Projects"
)
app_email = "admin@egc-me.com"
app_license = "mit"

required_apps = ["frappe", "erpnext"]

add_to_apps_screen = [
	{
		"name": "egc_projects",
		"logo": "/assets/egc_projects/images/logo.svg",
		"title": "EGC Projects",
		"route": "/app/egc-projects",
	}
]

# Includes in <head>
# ------------------

app_include_css = "egc_projects.bundle.css"
app_include_js = "egc_projects.bundle.js"

# The EGC Projects entry point is added to the standard ERPNext Project form rather than as a
# custom field, so nothing is written into the core Project schema.
doctype_js = {
	"Project": "public/js/project.js",
}

# Installation
# ------------

after_install = "egc_projects.install.after_install"
after_migrate = "egc_projects.install.after_migrate"

# Document Events
# ---------------

doc_events = {
	"EGC Project Document Revision": {
		"on_submit": "egc_projects.egc_projects.document_control.on_revision_submit",
		"on_cancel": "egc_projects.egc_projects.document_control.on_revision_cancel",
		"on_trash": "egc_projects.egc_projects.document_control.on_revision_trash",
	},
	"EGC Submittal Revision": {
		"on_submit": "egc_projects.egc_projects.submittal_control.on_submission_submit",
		"on_cancel": "egc_projects.egc_projects.submittal_control.on_submission_cancel",
		"on_trash": "egc_projects.egc_projects.submittal_control.on_submission_trash",
	},
	# `Project` is core, so it can't carry its own doctype-owned `validate()` overrides — these
	# two hooks stand in for that. Order matters only in that both must run after core's own
	# controller validate() (which Frappe always dispatches first for the same event) — see
	# project_progress.py's module docstring for why that ordering is what makes the second
	# hook here work at all.
	"Project": {
		"validate": [
			"egc_projects.egc_projects.project_custom_fields.validate_project",
			"egc_projects.egc_projects.project_progress.sync_project_percent_complete",
		],
		"after_insert": ["egc_projects.egc_projects.project_files.provision_project_folders"],
	},
	# One extra `validate` handler each, on every doctype the Hub's own Export/Import feature
	# covers (api/bulk_transfer.py) — a no-op outside of that feature's own controlled import
	# window, and the ONLY thing standing between an uploaded spreadsheet and injecting/reassigning
	# rows across a project boundary, since Frappe's own Importer has no concept of "Project" at
	# all. Runs after each doctype's own controller `validate()`, same ordering guarantee `Project`
	# above already relies on.
	"EGC WBS Node": {
		"validate": "egc_projects.api.bulk_transfer.enforce_bulk_import_project",
	},
	"EGC Activity": {
		"validate": "egc_projects.api.bulk_transfer.enforce_bulk_import_project",
	},
	"EGC Submittal": {
		"validate": "egc_projects.api.bulk_transfer.enforce_bulk_import_project",
	},
	"EGC Project Document": {
		"validate": "egc_projects.api.bulk_transfer.enforce_bulk_import_project",
	},
}

# Scheduled Tasks
# ---------------
# Mirrors egc_hr's own alert_expiring_documents pattern: a daily digest, deduped per
# reviewer/step/day inside the function itself (see notifications.py), not a real-time job.

scheduler_events = {
	"daily": [
		"egc_projects.egc_projects.notifications.send_due_date_reminders",
		"egc_projects.egc_projects.notifications.send_activity_due_date_reminders",
	],
}

# Fixtures
# --------
# Roles are also created by install.py; the fixture keeps them exportable/importable for
# sites that install from a built image rather than running after_install.

fixtures = [
	{
		"doctype": "Role",
		"filters": [
			[
				"name",
				"in",
				[
					"EGC Project Manager",
					"EGC Project Engineer",
					"EGC Document Controller",
					"EGC Project Viewer",
					"EGC External Viewer",
				],
			]
		],
	},
]

# Testing
# -------

# before_tests = "egc_projects.tests.utils.before_tests"

# Automatically update python controller files with type annotations for this app.
export_python_type_annotations = True
