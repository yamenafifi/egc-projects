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
