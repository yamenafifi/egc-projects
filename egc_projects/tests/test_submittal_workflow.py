"""Tests for the v2 multi-step Submittal review engine (docs/ARCHITECTURE_V2.md §7):
`EGC Submittal Workflow Template`, `EGC Submittal Review Step`, `submittal_control.py`'s
`apply_workflow_template`/`start_review`/`record_step_response`/`_evaluate_stage`, Ball in
Court, and `api/submittals.py`.

Fixture style matches `test_submittal.py` exactly (same helper shapes) plus `_get_or_create_user`
from `test_hub_api.py`'s additive-roles pattern for the identity-based permission tests.
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from egc_projects.api import submittals as submittals_api
from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import submittal_control


def _get_or_create_document_type():
	if not frappe.db.exists("EGC Document Type", "Drawing"):
		frappe.get_doc(
			{"doctype": "EGC Document Type", "document_type_name": "Drawing", "is_drawing": 1}
		).insert(ignore_permissions=True)
	return "Drawing"


def _get_or_create_discipline():
	if not frappe.db.exists("EGC Discipline", "MECH"):
		frappe.get_doc({"doctype": "EGC Discipline", "discipline_code": "MECH", "discipline_name": "Mechanical"}).insert(
			ignore_permissions=True
		)
	return "MECH"


def _get_or_create_submittal_type():
	if not frappe.db.exists("EGC Submittal Type", "Shop Drawing"):
		frappe.get_doc({"doctype": "EGC Submittal Type", "submittal_type_name": "Shop Drawing"}).insert(
			ignore_permissions=True
		)
	return "Shop Drawing"


def _get_or_create_stakeholder_role(name, is_egc_internal=0):
	if not frappe.db.exists("EGC Stakeholder Role", name):
		frappe.get_doc(
			{"doctype": "EGC Stakeholder Role", "role_name": name, "is_egc_internal": is_egc_internal}
		).insert(ignore_permissions=True)
	return name


def _get_or_create_user(email, roles):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user.set("roles", [])
	for role in roles:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return user.name


def _make_project(company):
	project = frappe.get_doc(
		{"doctype": "Project", "project_name": f"_Test Submittal Workflow {frappe.generate_hash(length=6)}", "company": company}
	)
	project.insert(ignore_permissions=True)
	return project.name


def _make_private_file():
	f = frappe.get_doc(
		{"doctype": "File", "file_name": f"{frappe.generate_hash(length=6)}.txt", "is_private": 1, "content": "x"}
	)
	f.insert(ignore_permissions=True)
	return f.file_url


class TestSubmittalWorkflow(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all("Company", limit=1, pluck="name")[0]
		cls.document_type = _get_or_create_document_type()
		cls.discipline = _get_or_create_discipline()
		cls.submittal_type = _get_or_create_submittal_type()

		cls.role_engineer = _get_or_create_stakeholder_role("EGC Project Engineer", is_egc_internal=1)
		cls.role_consultant = _get_or_create_stakeholder_role("Consultant", is_egc_internal=0)
		cls.role_oem = _get_or_create_stakeholder_role("OEM", is_egc_internal=0)

		cls.consultant_user = _get_or_create_user(
			"egc-swf-consultant@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER]
		)
		cls.manager_user = _get_or_create_user(
			"egc-swf-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)

	def setUp(self):
		self.project = _make_project(self.company)
		self._set_stakeholder(self.project, self.role_consultant, self.consultant_user, "Consultant Co")
		# OEM deliberately has NO reviewer_user — a pure external party with no Frappe login,
		# exercising the "is_external_only" / reviewer_label-only path.
		self._set_stakeholder(self.project, self.role_oem, None, "Siemens Healthineers")

	def tearDown(self):
		frappe.set_user("Administrator")

	# -- fixtures ------------------------------------------------------------------------------

	def _set_stakeholder(self, project, role, user, party_name):
		if not frappe.db.exists("EGC Project Profile", project):
			profile = frappe.new_doc("EGC Project Profile")
			profile.project = project
		else:
			profile = frappe.get_doc("EGC Project Profile", project)
		profile.append("stakeholders", {"role": role, "party_name": party_name, "user": user})
		profile.save(ignore_permissions=True)

	def _make_document(self, document_number="DOC-001"):
		doc = frappe.get_doc(
			{
				"doctype": "EGC Project Document",
				"project": self.project,
				"document_number": document_number,
				"title": document_number,
				"document_type": self.document_type,
				"discipline": self.discipline,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_issued_revision(self, document, revision):
		rev = frappe.get_doc(
			{
				"doctype": "EGC Project Document Revision",
				"document": document,
				"revision": revision,
				"file": _make_private_file(),
				"revision_date": today(),
			}
		)
		rev.insert(ignore_permissions=True)
		rev.submit()
		return rev

	def _make_submittal(self, submittal_number="SUB-001", **kwargs):
		values = {
			"doctype": "EGC Submittal",
			"project": self.project,
			"submittal_number": submittal_number,
			"title": kwargs.pop("title", submittal_number),
			"submittal_type": self.submittal_type,
			"discipline": self.discipline,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_draft_submission(self, submittal, revision_label, document_revisions):
		sub = frappe.get_doc(
			{
				"doctype": "EGC Submittal Revision",
				"submittal": submittal,
				"revision_label": revision_label,
				"date_submitted": today(),
			}
		)
		for rev_name in document_revisions:
			sub.append("documents", {"document_revision": rev_name})
		sub.insert(ignore_permissions=True)
		return sub

	def _make_template(self, name, steps):
		if frappe.db.exists("EGC Submittal Workflow Template", name):
			frappe.delete_doc("EGC Submittal Workflow Template", name, force=True)
		doc = frappe.get_doc(
			{"doctype": "EGC Submittal Workflow Template", "template_name": name, "steps": steps}
		)
		doc.insert(ignore_permissions=True)
		return doc

	def _build_submission_with_two_stage_workflow(self):
		"""Stage 1 (sequence 0): Engineer required. Stage 2 (sequence 1): Consultant required,
		OEM optional (no login)."""
		doc = self._make_document("DOC-WF-1")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-WF-1", submittal_manager=self.manager_user)
		submission = self._make_draft_submission(submittal.name, "00", [rev.name])

		steps = [
			frappe.get_doc(
				{
					"doctype": "EGC Submittal Review Step",
					"submittal_revision": submission.name,
					"sequence": 0,
					"reviewer_role": self.role_engineer,
					"reviewer_user": self.manager_user,
					"reviewer_label": "Ahmed Al-Otaibi",
					"is_required": 1,
				}
			).insert(ignore_permissions=True),
			frappe.get_doc(
				{
					"doctype": "EGC Submittal Review Step",
					"submittal_revision": submission.name,
					"sequence": 1,
					"reviewer_role": self.role_consultant,
					"reviewer_user": self.consultant_user,
					"reviewer_label": "Consultant Co",
					"is_required": 1,
				}
			).insert(ignore_permissions=True),
			frappe.get_doc(
				{
					"doctype": "EGC Submittal Review Step",
					"submittal_revision": submission.name,
					"sequence": 1,
					"reviewer_role": self.role_oem,
					"reviewer_user": None,
					"reviewer_label": "Siemens Healthineers",
					"is_required": 0,
				}
			).insert(ignore_permissions=True),
		]
		return submittal, submission, steps

	# -- apply_workflow_template ------------------------------------------------------------

	def test_apply_workflow_template_resolves_reviewer_and_creates_steps(self):
		doc = self._make_document("DOC-TMPL-1")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-TMPL-1")
		submission = self._make_draft_submission(submittal.name, "00", [rev.name])

		template = self._make_template(
			"Standard Consultant Review",
			[{"sequence": 0, "reviewer_role": self.role_consultant, "is_required": 1}],
		)

		created = submittal_control.apply_workflow_template(submission.name, template.name)
		self.assertEqual(len(created), 1)
		step = frappe.get_doc("EGC Submittal Review Step", created[0])
		self.assertEqual(step.reviewer_user, self.consultant_user)
		self.assertEqual(step.status, c.STEP_PENDING)

	def test_apply_workflow_template_rejected_when_steps_already_exist(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		template = self._make_template("Dup Test", [{"sequence": 0, "reviewer_role": self.role_consultant}])
		with self.assertRaises(frappe.ValidationError):
			submittal_control.apply_workflow_template(submission.name, template.name)

	# -- start_review / staged progression ---------------------------------------------------

	def test_submit_with_steps_opens_only_first_stage(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()

		step_rows = {s.name: frappe.get_doc("EGC Submittal Review Step", s.name) for s in steps}
		stage0 = [s for s in steps if frappe.db.get_value("EGC Submittal Review Step", s.name, "sequence") == 0]
		stage1 = [s for s in steps if frappe.db.get_value("EGC Submittal Review Step", s.name, "sequence") == 1]

		for s in stage0:
			self.assertEqual(frappe.db.get_value("EGC Submittal Review Step", s.name, "status"), c.STEP_IN_REVIEW)
		for s in stage1:
			self.assertEqual(frappe.db.get_value("EGC Submittal Review Step", s.name, "status"), c.STEP_PENDING)

		submission.reload()
		self.assertEqual(submission.submission_status, c.SUBMISSION_SUBMITTED)

	def test_ball_in_court_reflects_current_stage(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()

		bic = submittal_control.get_ball_in_court(submission.name)
		self.assertIn(self.manager_user, bic["users"])
		self.assertNotIn(self.consultant_user, bic["users"])

		# ball_in_court_label (stored) is a role-prefixed joined summary of the SAME live data
		# get_ball_in_court() exposes as raw parts — not the identical string, by design (a
		# frontend wants the raw list to format itself; the stored field is a ready-to-print
		# fallback). Assert the underlying identity, not string equality between the two shapes.
		submission.reload()
		self.assertIn("Ahmed Al-Otaibi", submission.ball_in_court_label)

		submittal.reload()
		self.assertEqual(submittal.ball_in_court, submission.ball_in_court_label)

	def test_stage_advances_only_after_all_required_steps_respond(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()

		stage0_step = next(
			s.name for s in steps if frappe.db.get_value("EGC Submittal Review Step", s.name, "sequence") == 0
		)
		frappe.set_user(self.manager_user)
		submittal_control.record_step_response(stage0_step, c.RESPONSE_APPROVED)

		# Stage 1 must now be In Review (advanced automatically).
		stage1_rows = frappe.get_all(
			"EGC Submittal Review Step", filters={"submittal_revision": submission.name, "sequence": 1}, fields=["reviewer_role", "status", "is_required"]
		)
		by_role = {r.reviewer_role: r for r in stage1_rows}
		self.assertEqual(by_role[self.role_consultant].status, c.STEP_IN_REVIEW)
		self.assertEqual(by_role[self.role_oem].status, c.STEP_IN_REVIEW)

		submission.reload()
		self.assertEqual(submission.submission_status, c.SUBMISSION_SUBMITTED)  # not yet Responded

	def test_optional_step_skipped_when_stage_clears_without_it(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()
		stage0_step = next(
			s.name for s in steps if frappe.db.get_value("EGC Submittal Review Step", s.name, "sequence") == 0
		)
		frappe.set_user(self.manager_user)
		submittal_control.record_step_response(stage0_step, c.RESPONSE_APPROVED)

		consultant_step = next(
			s.name
			for s in steps
			if frappe.db.get_value("EGC Submittal Review Step", s.name, "reviewer_role") == self.role_consultant
		)
		frappe.set_user(self.consultant_user)
		submittal_control.record_step_response(consultant_step, c.RESPONSE_APPROVED)

		oem_step = next(
			s.name for s in steps if frappe.db.get_value("EGC Submittal Review Step", s.name, "reviewer_role") == self.role_oem
		)
		self.assertEqual(frappe.db.get_value("EGC Submittal Review Step", oem_step, "status"), c.STEP_SKIPPED)

		submission.reload()
		self.assertEqual(submission.submission_status, c.SUBMISSION_RESPONDED)
		self.assertEqual(submission.response, c.RESPONSE_APPROVED)

	def test_single_terminal_response_stops_workflow_immediately(self):
		"""One reviewer sending Revise & Resubmit ends the cycle right away — it does not wait
		for the other required reviewer at the same stage."""
		doc = self._make_document("DOC-TERM-1")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-TERM-1")
		submission = self._make_draft_submission(submittal.name, "00", [rev.name])
		frappe.get_doc(
			{
				"doctype": "EGC Submittal Review Step",
				"submittal_revision": submission.name,
				"sequence": 0,
				"reviewer_role": self.role_engineer,
				"reviewer_user": self.manager_user,
				"is_required": 1,
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "EGC Submittal Review Step",
				"submittal_revision": submission.name,
				"sequence": 0,
				"reviewer_role": self.role_consultant,
				"reviewer_user": self.consultant_user,
				"is_required": 1,
			}
		).insert(ignore_permissions=True)

		submission.submit()
		frappe.set_user(self.manager_user)
		submittal_control.record_step_response(
			frappe.get_all(
				"EGC Submittal Review Step",
				filters={"submittal_revision": submission.name, "reviewer_user": self.manager_user},
				pluck="name",
			)[0],
			c.RESPONSE_REVISE_AND_RESUBMIT,
			remarks="Needs rework",
		)

		submission.reload()
		self.assertEqual(submission.submission_status, c.SUBMISSION_RESPONDED)
		self.assertEqual(submission.response, c.RESPONSE_REVISE_AND_RESUBMIT)

		# The consultant's step never got a chance to respond — a single terminal response ends
		# the submission immediately without fabricating a response for every other reviewer,
		# but leaving their step open forever (still In Review, with a live assignment) against
		# an already-Responded submission would be stale, confusing state. It is Skipped and its
		# assignment closed instead.
		consultant_step = frappe.get_all(
			"EGC Submittal Review Step",
			filters={"submittal_revision": submission.name, "reviewer_user": self.consultant_user},
			fields=["status"],
		)[0]
		self.assertEqual(consultant_step.status, c.STEP_SKIPPED)

	def test_final_response_all_approved_is_approved(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()
		stage0_step = next(
			s.name for s in steps if frappe.db.get_value("EGC Submittal Review Step", s.name, "sequence") == 0
		)
		frappe.set_user(self.manager_user)
		submittal_control.record_step_response(stage0_step, c.RESPONSE_APPROVED)
		consultant_step = next(
			s.name
			for s in steps
			if frappe.db.get_value("EGC Submittal Review Step", s.name, "reviewer_role") == self.role_consultant
		)
		frappe.set_user(self.consultant_user)
		submittal_control.record_step_response(consultant_step, c.RESPONSE_APPROVED)

		submittal.reload()
		self.assertEqual(submittal.submittal_status, c.RESPONSE_APPROVED)

	def test_final_response_mixed_approved_with_comments(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()
		stage0_step = next(
			s.name for s in steps if frappe.db.get_value("EGC Submittal Review Step", s.name, "sequence") == 0
		)
		frappe.set_user(self.manager_user)
		submittal_control.record_step_response(stage0_step, c.RESPONSE_APPROVED_WITH_COMMENTS, remarks="Minor note")
		consultant_step = next(
			s.name
			for s in steps
			if frappe.db.get_value("EGC Submittal Review Step", s.name, "reviewer_role") == self.role_consultant
		)
		frappe.set_user(self.consultant_user)
		submittal_control.record_step_response(consultant_step, c.RESPONSE_APPROVED)

		submittal.reload()
		self.assertEqual(submittal.submittal_status, c.RESPONSE_APPROVED_WITH_COMMENTS)

	# -- identity-based authorization -------------------------------------------------------

	def test_record_step_response_rejected_for_non_assigned_user(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()
		stage0_step = next(
			s.name for s in steps if frappe.db.get_value("EGC Submittal Review Step", s.name, "sequence") == 0
		)
		frappe.set_user(self.consultant_user)  # not the assigned reviewer for this step
		with self.assertRaises(frappe.PermissionError):
			submittal_control.record_step_response(stage0_step, c.RESPONSE_APPROVED)

	def test_record_step_response_allowed_for_internal_override(self):
		"""An EGC Project Manager may record a response on behalf of a reviewer who has no
		Frappe login (e.g. relaying an approval received by email)."""
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()
		stage0_step = next(
			s.name for s in steps if frappe.db.get_value("EGC Submittal Review Step", s.name, "sequence") == 0
		)
		# manager_user IS the assigned reviewer here, so use a fresh override user instead.
		override_user = _get_or_create_user("egc-swf-override@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER])
		frappe.set_user(override_user)
		submittal_control.record_step_response(stage0_step, c.RESPONSE_APPROVED)
		self.assertEqual(frappe.db.get_value("EGC Submittal Review Step", stage0_step, "status"), c.STEP_RESPONDED)

	def test_step_fields_cannot_be_hand_edited(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		step = frappe.get_doc("EGC Submittal Review Step", steps[0].name)
		step.status = c.STEP_RESPONDED
		with self.assertRaises(frappe.ValidationError):
			step.save()

	# -- v1 backward compatibility (no steps at all) -----------------------------------------

	def test_submission_with_no_steps_behaves_exactly_as_v1(self):
		doc = self._make_document("DOC-NOSTEPS-1")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-NOSTEPS-1")
		submission = self._make_draft_submission(submittal.name, "00", [rev.name])
		submission.submit()

		submission.reload()
		self.assertEqual(submission.submission_status, c.SUBMISSION_SUBMITTED)
		self.assertIsNone(submission.ball_in_court_label)

		submittal_control.record_response(submission.name, c.RESPONSE_APPROVED)
		submission.reload()
		self.assertEqual(submission.response, c.RESPONSE_APPROVED)

	# -- api/submittals.py --------------------------------------------------------------------

	def test_create_submittal_endpoint(self):
		frappe.set_user(self.manager_user)
		result = submittals_api.create_submittal(
			self.project,
			submittal_number="SUB-API-1",
			title="API Created Submittal",
			submittal_type=self.submittal_type,
		)
		self.assertTrue(frappe.db.exists("EGC Submittal", result["name"]))

	def test_get_submittal_detail_includes_steps_and_documents(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()

		detail = submittals_api.get_submittal_detail(submittal.name)
		self.assertEqual(len(detail["submissions"]), 1)
		self.assertEqual(len(detail["submissions"][0]["steps"]), 3)
		self.assertEqual(len(detail["submissions"][0]["documents"]), 1)

	def test_workflow_template_create_and_list_endpoints(self):
		name = submittals_api.create_workflow_template(
			"API Template Test",
			[{"sequence": 0, "reviewer_role": self.role_consultant, "is_required": 1}],
		)
		templates = submittals_api.get_workflow_templates()
		self.assertIn(name, [t["name"] for t in templates])
		frappe.delete_doc("EGC Submittal Workflow Template", name, force=True)

	def test_workflow_template_create_accepts_json_string_steps(self):
		"""Regression, same class as the WBS bulk-create fix: a real browser call sends `steps`
		as a JSON string, not a Python list."""
		import json

		name = submittals_api.create_workflow_template(
			"API Template JSON Test",
			json.dumps([{"sequence": 0, "reviewer_role": self.role_consultant, "is_required": 1}]),
		)
		self.assertTrue(frappe.db.exists("EGC Submittal Workflow Template", name))
		frappe.delete_doc("EGC Submittal Workflow Template", name, force=True)

	def test_get_my_open_reviews_scoped_to_current_user(self):
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()

		frappe.set_user(self.manager_user)
		mine = submittals_api.get_my_open_reviews()
		self.assertTrue(any(row["submittal"] == submittal.name for row in mine))

		frappe.set_user(self.consultant_user)
		mine_consultant = submittals_api.get_my_open_reviews()
		self.assertFalse(any(row["submittal"] == submittal.name for row in mine_consultant))
