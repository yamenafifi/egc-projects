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
from egc_projects.egc_projects import assignments, constants as c, relationships
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
		cls.engineer_user = _get_or_create_user(
			"egc-swf-engineer@example.com", ["Projects User", c.ROLE_PROJECT_ENGINEER]
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
		doc = frappe.get_doc("Project", project)
		doc.append("custom_egc_stakeholders", {"role": role, "party_name": party_name, "person": user})
		doc.save(ignore_permissions=True)

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

	def test_ball_in_court_propagates_to_submittal_on_stage_transition(self):
		"""Regression: `_refresh_ball_in_court` used to write only the submission's own
		`ball_in_court_label` — the Submittal-level `ball_in_court` (what the Hub register and
		detail drawer actually display) was refreshed only by the terminal/lifecycle paths, so a
		mid-workflow stage advance left it stuck on the PREVIOUS stage's reviewer until the whole
		submission resolved. Found live: stage 0 (Project Engineer) approved, stage 1 (Consultant
		+ optional OEM) correctly opened, but the Submittal header kept showing stage 0's name."""
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		submission.submit()

		submittal.reload()
		self.assertIn("Ahmed Al-Otaibi", submittal.ball_in_court)

		stage0_step = next(
			s.name for s in steps if frappe.db.get_value("EGC Submittal Review Step", s.name, "sequence") == 0
		)
		frappe.set_user(self.manager_user)
		submittal_control.record_step_response(stage0_step, c.RESPONSE_APPROVED)

		submittal.reload()
		self.assertNotIn("Ahmed Al-Otaibi", submittal.ball_in_court)
		self.assertIn("Consultant Co", submittal.ball_in_court)

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
		# The blocking reviewer's own remarks must propagate up to the SUBMISSION's own
		# response_remarks, not just sit on their step row — that's what the Hub's "why" line
		# reads for a step-based rejection/resubmit-request.
		self.assertEqual(submission.response_remarks, "Needs rework")

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

	def test_engineer_cannot_self_assign_someone_elses_step(self):
		"""Regression for a real hole: `EGC Submittal Review Step` used to grant `EGC Project
		Engineer` blanket doctype-level `write: 1`, and `reviewer_user` is neither engine-guarded
		(`assert_step_engine_authorized` only covers status/response/response_date/responded_by/
		response_remarks/response_attachment) nor read_only. Combined with `record_step_response`
		authorizing purely by identity ("are you `reviewer_user`"), an Engineer with no
		relationship to a step could set `reviewer_user = themselves` and then pass that identity
		check on any pending/in-review step on any project — completely undermining the
		identity-based security model the rest of the step engine relies on. The fix removes the
		doctype-level write grant; legitimate Engineer step management still goes through
		`add_review_step`/`apply_workflow_template`, which authorize on `EGC Submittal Revision`
		write instead."""
		submittal, submission, steps = self._build_submission_with_two_stage_workflow()
		step_name = steps[0].name
		self.assertNotEqual(
			frappe.db.get_value("EGC Submittal Review Step", step_name, "reviewer_user"), self.engineer_user
		)

		frappe.set_user(self.engineer_user)
		step = frappe.get_doc("EGC Submittal Review Step", step_name)
		step.reviewer_user = self.engineer_user
		with self.assertRaises(frappe.PermissionError):
			step.save()

	def test_engineer_can_originate_and_submit_a_submittal(self):
		"""Regression for the flip side of the security fix above: EGC Project Engineer used to
		be read-only on EGC Submittal/EGC Submittal Revision, silently breaking the Hub's own
		"+ New Submittal" button for that role (`SubmittalsTab.vue`'s own `canWrite` gate already
		shows it to Engineers) and contradicting the build brief's own workflow example, which
		puts the Project Engineer first as the originator. Engineer now has create/write
		(Submittal) and create/write/submit (Submittal Revision) — verified end to end through
		the real api/submittals.py functions, not just a doctype has_permission check."""
		from egc_projects.api import submittals as submittals_api

		doc = self._make_document("DOC-ENGCREATE-1")
		rev = self._make_issued_revision(doc.name, "00")

		frappe.set_user(self.engineer_user)
		result = submittals_api.create_submittal(
			self.project,
			submittal_number="SUB-ENGCREATE-1",
			title="Engineer Originated",
			submittal_type=self.submittal_type,
			discipline=self.discipline,
		)
		submission = submittals_api.create_first_submission(result["name"])["name"]
		submittals_api.add_submission_document(submission, rev.name)
		submittals_api.submit_submission(submission)

		self.assertEqual(
			frappe.db.get_value("EGC Submittal Revision", submission, "submission_status"), c.SUBMISSION_SUBMITTED
		)

	def test_direct_save_cannot_bypass_cross_submittal_exclusivity(self):
		"""The "one document revision under review through only one submittal at a time" rule
		used to live only in `api/submittals.py.add_submission_document()` — a raw
		`doc.append(...); doc.insert()`/`.save()` bypassed it entirely. It now lives in
		`EGCSubmittalRevision._validate_documents()` itself, so it fires on every save path,
		exactly like `_make_draft_submission()` here (a raw insert, not the whitelisted
		endpoint)."""
		doc = self._make_document("DOC-EXCL-1")
		rev = self._make_issued_revision(doc.name, "00")
		submittal_a = self._make_submittal("SUB-EXCL-A")
		self._make_draft_submission(submittal_a.name, "00", [rev.name])

		submittal_b = self._make_submittal("SUB-EXCL-B")
		with self.assertRaises(frappe.ValidationError):
			self._make_draft_submission(submittal_b.name, "00", [rev.name])

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

	# -- add_submission_document: a document revision can only be live in ONE submittal ------

	def test_document_revision_cannot_be_attached_to_two_open_submittals(self):
		doc = self._make_document("DOC-EXCL-1")
		rev = self._make_issued_revision(doc.name, "00")

		holder = self._make_submittal("SUB-EXCL-HOLDER")
		other = self._make_submittal("SUB-EXCL-OTHER")

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(holder.name)
		submittals_api.add_submission_document(s1["name"], rev.name)

		s2 = submittals_api.create_first_submission(other.name)
		with self.assertRaises(frappe.ValidationError):
			submittals_api.add_submission_document(s2["name"], rev.name)

	def test_document_revision_can_move_to_next_revision_of_same_submittal(self):
		doc = self._make_document("DOC-EXCL-2")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-EXCL-SAME")

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)
		submittals_api.add_submission_document(s1["name"], rev.name)
		submittals_api.submit_submission(s1["name"])
		submittal_control.record_response(s1["name"], c.RESPONSE_REVISE_AND_RESUBMIT)

		s2_name = submittal_control.create_next_revision(submittal.name)
		# Re-attaching the SAME document revision to a later revision of the SAME submittal is
		# the ordinary resubmission case and must stay allowed.
		submittals_api.add_submission_document(s2_name, rev.name)

	def test_document_revision_frees_up_once_its_submission_is_cancelled(self):
		doc = self._make_document("DOC-EXCL-3")
		rev = self._make_issued_revision(doc.name, "00")

		holder = self._make_submittal("SUB-EXCL-CANCEL-HOLDER")
		other = self._make_submittal("SUB-EXCL-CANCEL-OTHER")

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(holder.name)
		submittals_api.add_submission_document(s1["name"], rev.name)
		submittals_api.submit_submission(s1["name"])

		frappe.set_user("Administrator")
		s1_doc = frappe.get_doc("EGC Submittal Revision", s1["name"])
		s1_doc.cancel()

		frappe.set_user(self.manager_user)
		s2 = submittals_api.create_first_submission(other.name)
		submittals_api.add_submission_document(s2["name"], rev.name)

	# -- delete_submittal: Draft-only, permanent history has no bypass -----------------------

	def test_delete_submittal_succeeds_when_every_revision_is_still_draft(self):
		submittal = self._make_submittal("SUB-DEL-DRAFT")
		frappe.set_user(self.manager_user)
		submittals_api.create_first_submission(submittal.name)

		submittals_api.delete_submittal(submittal.name)
		self.assertFalse(frappe.db.exists("EGC Submittal", submittal.name))

	def test_delete_submittal_with_submitted_history_is_refused_for_every_role(self):
		doc = self._make_document("DOC-DEL-1")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-DEL-HISTORY")

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)
		submittals_api.add_submission_document(s1["name"], rev.name)
		submittals_api.submit_submission(s1["name"])

		with self.assertRaises(frappe.ValidationError):
			submittals_api.delete_submittal(submittal.name)

		# Not even a System Manager can delete it through this API — history is permanent,
		# not merely role-gated.
		frappe.set_user("Administrator")
		with self.assertRaises(frappe.ValidationError):
			submittals_api.delete_submittal(submittal.name)
		self.assertTrue(frappe.db.exists("EGC Submittal", submittal.name))

	# -- update_submission_dates ---------------------------------------------------------------

	def test_update_submission_dates_sets_only_provided_fields(self):
		submittal = self._make_submittal("SUB-DATES-1")
		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)

		submittals_api.update_submission_dates(s1["name"], due_date="2026-09-01", lead_time_days=14)

		sub = frappe.get_doc("EGC Submittal Revision", s1["name"])
		self.assertEqual(str(sub.due_date), "2026-09-01")
		self.assertEqual(sub.lead_time_days, 14)
		self.assertIsNone(sub.required_submission_date)

	def test_update_submission_dates_still_settable_once_submitted(self):
		"""These are plain planning/reference fields, not engine state — nothing about being
		submitted should freeze them (e.g. logging a client's verbally-committed approval date
		after the package already went out)."""
		doc = self._make_document("DOC-DATES-2")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-DATES-2")

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)
		submittals_api.add_submission_document(s1["name"], rev.name)
		submittals_api.submit_submission(s1["name"])

		submittals_api.update_submission_dates(s1["name"], due_date="2026-09-01", lead_time_days=21)

		sub = frappe.get_doc("EGC Submittal Revision", s1["name"])
		self.assertEqual(str(sub.due_date), "2026-09-01")
		self.assertEqual(sub.lead_time_days, 21)

	# -- on_submission_submit sets date_submitted ------------------------------------------------

	def test_submit_sets_date_submitted(self):
		doc = self._make_document("DOC-DATESUB-1")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-DATESUB-1")

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)
		submittals_api.add_submission_document(s1["name"], rev.name)
		submittals_api.submit_submission(s1["name"])

		sub = frappe.get_doc("EGC Submittal Revision", s1["name"])
		self.assertEqual(str(sub.date_submitted), today())

	# -- ball-in-court falls to whoever owns resubmitting after a Rejected/Revise & Resubmit ----

	def _make_person(self, full_name):
		# A "person" IS a User — see test_directory.py's own `_make_person` docstring for why
		# `first_name` alone reproduces `full_name` exactly for these single-string test names.
		return frappe.get_doc(
			{
				"doctype": "User",
				"email": f"egc-sw-test-{frappe.generate_hash(length=10)}@example.com",
				"first_name": full_name,
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)

	def test_ball_in_court_falls_to_submittal_responsible_after_rejection(self):
		doc = self._make_document("DOC-BIC-1")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-BIC-1")
		person = self._make_person("BIC Responsible One")
		assignments.add_assignment("EGC Submittal", submittal.name, "Responsible", person=person.name, is_primary=True)

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)
		submittals_api.add_submission_document(s1["name"], rev.name)
		submittals_api.submit_submission(s1["name"])
		submittal_control.record_response(s1["name"], c.RESPONSE_REJECTED)

		submittal.reload()
		self.assertIn("BIC Responsible One", submittal.ball_in_court)
		self.assertIn("resubmission needed", submittal.ball_in_court)

	def test_ball_in_court_updates_when_responsible_assigned_after_the_fact(self):
		"""The realistic order of events: reject first (nobody's Responsible yet, so Ball in
		Court is empty), THEN hand ownership to someone — that assignment write must itself
		refresh Ball in Court, not just the next unrelated engine event."""
		doc = self._make_document("DOC-BIC-5")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-BIC-5")

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)
		submittals_api.add_submission_document(s1["name"], rev.name)
		submittals_api.submit_submission(s1["name"])
		submittal_control.record_response(s1["name"], c.RESPONSE_REJECTED)

		submittal.reload()
		self.assertFalse(submittal.ball_in_court)

		person = self._make_person("BIC Responsible Five")
		assignments.add_assignment("EGC Submittal", submittal.name, "Responsible", person=person.name, is_primary=True)

		submittal.reload()
		self.assertIn("BIC Responsible Five", submittal.ball_in_court)

		assignment_name = frappe.db.get_value(
			"EGC Assignment", {"parent_name": submittal.name, "person": person.name}, "name"
		)
		assignments.remove_assignment(assignment_name)

		submittal.reload()
		self.assertFalse(submittal.ball_in_court)

	def test_ball_in_court_falls_back_to_linked_activity_responsible(self):
		doc = self._make_document("DOC-BIC-2")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-BIC-2")
		person = self._make_person("BIC Responsible Two")

		activity = frappe.get_doc(
			{
				"doctype": "EGC Activity",
				"project": self.project,
				"activity_code": "BIC-ACT-2",
				"activity_name": "BIC Test Activity 2",
			}
		).insert(ignore_permissions=True)
		relationships.add_link(activity.name, "EGC Submittal", submittal.name)
		assignments.add_assignment("EGC Activity", activity.name, "Responsible", person=person.name, is_primary=True)

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)
		submittals_api.add_submission_document(s1["name"], rev.name)
		submittals_api.submit_submission(s1["name"])
		submittal_control.record_response(s1["name"], c.RESPONSE_REVISE_AND_RESUBMIT)

		submittal.reload()
		self.assertIn("BIC Responsible Two", submittal.ball_in_court)

	def test_ball_in_court_stays_empty_with_no_responsible_anywhere(self):
		doc = self._make_document("DOC-BIC-3")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-BIC-3")

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)
		submittals_api.add_submission_document(s1["name"], rev.name)
		submittals_api.submit_submission(s1["name"])
		submittal_control.record_response(s1["name"], c.RESPONSE_REJECTED)

		submittal.reload()
		self.assertFalse(submittal.ball_in_court)

	def test_ball_in_court_not_affected_when_response_is_approved(self):
		doc = self._make_document("DOC-BIC-4")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-BIC-4")
		person = self._make_person("BIC Responsible Four")
		assignments.add_assignment("EGC Submittal", submittal.name, "Responsible", person=person.name, is_primary=True)

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)
		submittals_api.add_submission_document(s1["name"], rev.name)
		submittals_api.submit_submission(s1["name"])
		submittal_control.record_response(s1["name"], c.RESPONSE_APPROVED)

		submittal.reload()
		self.assertFalse(submittal.ball_in_court)

	# -- get_submittal_detail: tracked_documents shows the live latest issued revision ----------

	def test_tracked_documents_reflects_live_current_revision(self):
		doc = self._make_document("DOC-TRACK-1")
		rev00 = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-TRACK-1")

		frappe.set_user(self.manager_user)
		s1 = submittals_api.create_first_submission(submittal.name)
		submittals_api.add_submission_document(s1["name"], rev00.name)

		detail = submittals_api.get_submittal_detail(submittal.name)
		self.assertEqual(len(detail["tracked_documents"]), 1)
		self.assertEqual(detail["tracked_documents"][0]["current_revision_label"], "00")

		frappe.set_user("Administrator")
		self._make_issued_revision(doc.name, "01")

		detail = submittals_api.get_submittal_detail(submittal.name)
		self.assertEqual(detail["tracked_documents"][0]["current_revision_label"], "01")

	def test_tracked_documents_empty_with_no_submission_yet(self):
		submittal = self._make_submittal("SUB-TRACK-2")
		detail = submittals_api.get_submittal_detail(submittal.name)
		self.assertEqual(detail["tracked_documents"], [])

	def test_get_documents_with_current_revision_resolves_by_document_not_revision(self):
		doc = self._make_document("DOC-RESOLVE-1")
		self._make_issued_revision(doc.name, "00")
		self._make_issued_revision(doc.name, "01")

		rows = submittals_api.get_documents_with_current_revision(self.project, [doc.name])
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["current_revision_label"], "01")
