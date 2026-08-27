# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Level 0 §7/§32 acceptance: an external party (a Consultant, say) assigned as a Submittal
reviewer must be able to log in, see the item in My Open Items, open the Submittal, and record
their own response — without needing an internal EGC role at all. `submittal_control.py`'s
`record_step_response` was already built identity-based ("are you the assigned reviewer", not
"do you hold role X") specifically for this; these tests are the first real end-to-end proof of
it working for a genuinely external (EGC External Viewer) account, not just an internal user
being informally trusted to only touch their own step.
"""

import frappe
from frappe.permissions import add_user_permission
from frappe.tests import IntegrationTestCase

from egc_projects.api import hub, submittals as submittals_api
from egc_projects.egc_projects import action_items, comments, constants as c, submittal_control


def _make_company():
	return frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]


def _make_project(company):
	doc = frappe.get_doc(
		{"doctype": "Project", "project_name": f"EGC-ExtRev-Test-{frappe.generate_hash(length=8)}", "company": company}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _get_or_create_user(email, roles):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		)
		user.insert(ignore_permissions=True)
	user.add_roles(*roles)
	return user.name


class TestExternalSubmittalReview(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = _make_company()

	def setUp(self):
		frappe.set_user("Administrator")
		self.project = _make_project(self.company)
		self.consultant = _get_or_create_user(
			f"egc-consultant-{frappe.generate_hash(length=6)}@example.com",
			["Projects User", c.ROLE_EXTERNAL_VIEWER],
		)
		add_user_permission("Project", self.project, self.consultant, ignore_permissions=True)

		submittal = frappe.get_doc(
			{
				"doctype": "EGC Submittal",
				"project": self.project,
				"submittal_number": "EXT-SUB-001",
				"title": "External Review Test",
				"submittal_type": "Product Data",
			}
		)
		submittal.insert(ignore_permissions=True)
		self.submittal = submittal.name

		revision = frappe.get_doc(
			{"doctype": "EGC Submittal Revision", "submittal": self.submittal, "revision_label": "00"}
		)
		revision.insert(ignore_permissions=True)
		self.revision = revision.name

		step = frappe.get_doc(
			{
				"doctype": "EGC Submittal Review Step",
				"submittal_revision": self.revision,
				"sequence": 0,
				"status": "In Review",
				"reviewer_user": self.consultant,
			}
		)
		step.insert(ignore_permissions=True)
		self.step = step.name

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_external_reviewer_can_view_submittal_detail(self):
		frappe.set_user(self.consultant)
		detail = submittals_api.get_submittal_detail(self.submittal)  # must not raise
		self.assertEqual(detail["submittal"]["name"], self.submittal)

	def test_external_reviewer_sees_it_in_my_open_items(self):
		frappe.set_user(self.consultant)
		items = hub.get_my_open_items(self.project)
		self.assertEqual({i["name"] for i in items}, {self.submittal})
		self.assertEqual(items[0]["source"], "submittal_review")

	def test_external_reviewer_can_record_their_own_response(self):
		frappe.set_user(self.consultant)
		submittal_control.record_step_response(self.step, "Approved", "Looks good.")

		step = frappe.get_doc("EGC Submittal Review Step", self.step)
		self.assertEqual(step.status, "Responded")
		self.assertEqual(step.response, "Approved")
		self.assertEqual(step.responded_by, self.consultant)

	def test_unassigned_external_user_cannot_respond_on_someone_elses_step(self):
		other_consultant = _get_or_create_user(
			f"egc-other-consultant-{frappe.generate_hash(length=6)}@example.com",
			["Projects User", c.ROLE_EXTERNAL_VIEWER],
		)
		add_user_permission("Project", self.project, other_consultant, ignore_permissions=True)

		frappe.set_user(other_consultant)
		with self.assertRaises(frappe.PermissionError):
			submittal_control.record_step_response(self.step, "Approved")

	def test_ball_in_court_updates_after_external_response(self):
		frappe.set_user(self.consultant)
		submittal_control.record_step_response(self.step, "Approved")

		self.assertIsNone(frappe.db.get_value("EGC Submittal", self.submittal, "ball_in_court"))

	def test_responding_removes_it_from_open_items(self):
		frappe.set_user(self.consultant)
		submittal_control.record_step_response(self.step, "Approved")
		self.assertEqual(action_items.get_open_items_for_user(self.consultant, self.project), [])

	def test_external_reviewer_can_attach_a_response_file(self):
		frappe.set_user(self.consultant)
		submittal_control.record_step_response(self.step, "Approved with Comments", "See markup.", "/files/markup.pdf")

		step = frappe.get_doc("EGC Submittal Review Step", self.step)
		self.assertEqual(step.response_attachment, "/files/markup.pdf")

	def test_response_attachment_is_engine_owned(self):
		step = frappe.get_doc("EGC Submittal Review Step", self.step)
		step.response_attachment = "/files/sneaky.pdf"
		with self.assertRaises(frappe.ValidationError):
			step.save(ignore_permissions=True)

	def test_external_reviewer_can_add_and_read_comments(self):
		frappe.set_user(self.consultant)
		comments.add_comment("EGC Submittal", self.submittal, "Looks good, approving.")

		thread = comments.get_comments("EGC Submittal", self.submittal)
		self.assertEqual(len(thread), 1)
		self.assertEqual(thread[0]["content"], "Looks good, approving.")
		self.assertEqual(thread[0]["owner"], self.consultant)

	def test_user_scoped_to_a_different_project_cannot_comment(self):
		# An External Viewer's read access is doctype-wide by role; the actual per-project fence
		# is the User Permission on Project — Frappe only enforces it once at least one such
		# record exists for the user, so the outsider needs one scoped to SOME OTHER project to
		# prove this Submittal's project is actually outside their reach.
		other_project = _make_project(self.company)
		outsider = _get_or_create_user(
			f"egc-outsider-{frappe.generate_hash(length=6)}@example.com",
			["Projects User", c.ROLE_EXTERNAL_VIEWER],
		)
		add_user_permission("Project", other_project, outsider, ignore_permissions=True)

		frappe.set_user(outsider)
		with self.assertRaises(frappe.PermissionError):
			comments.add_comment("EGC Submittal", self.submittal, "Should not be allowed.")

	def test_empty_comment_rejected(self):
		frappe.set_user(self.consultant)
		with self.assertRaises(frappe.ValidationError):
			comments.add_comment("EGC Submittal", self.submittal, "   ")
