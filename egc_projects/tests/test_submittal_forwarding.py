"""Live "forward to next reviewer" routing at response time — the transmittal-style hop layered
on top of the pre-planned stage/sequence engine in `submittal_control.py` (see that module's own
`record_step_response`/`_evaluate_stage`/`_apply_forward` docstrings). Reuses
`test_submittal_workflow.py`'s free fixture helper functions (they take no `self`, so they're
safe to import directly rather than duplicated or inherited).
"""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from egc_projects.egc_projects import constants as c, submittal_control
from egc_projects.tests.test_submittal_workflow import (
	_get_or_create_discipline,
	_get_or_create_document_type,
	_get_or_create_stakeholder_role,
	_get_or_create_submittal_type,
	_get_or_create_user,
	_make_private_file,
	_make_project,
)


class TestSubmittalForwarding(IntegrationTestCase):
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

		cls.user_a = _get_or_create_user("egc-fwd-a@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER])
		cls.user_b = _get_or_create_user("egc-fwd-b@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER])
		cls.user_c = _get_or_create_user("egc-fwd-c@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER])
		# No internal EGC role at all — the exact population this feature exists for (an external
		# reviewer forwarding their own step from their own low-privilege session).
		cls.external_user = _get_or_create_user("egc-fwd-external@example.com", ["Projects User", c.ROLE_EXTERNAL_VIEWER])

	def setUp(self):
		self.project = _make_project(self.company)

	def tearDown(self):
		frappe.set_user("Administrator")

	# -- fixtures (mirrors test_submittal_workflow.py's own shapes) ----------------------------

	def _make_document(self, document_number="DOC-FWD-1"):
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

	def _make_submittal(self, submittal_number="SUB-FWD-1"):
		doc = frappe.get_doc(
			{
				"doctype": "EGC Submittal",
				"project": self.project,
				"submittal_number": submittal_number,
				"title": submittal_number,
				"submittal_type": self.submittal_type,
				"discipline": self.discipline,
			}
		)
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

	def _add_step(self, submission, sequence, reviewer_user, is_required=1):
		step = frappe.get_doc(
			{
				"doctype": "EGC Submittal Review Step",
				"submittal_revision": submission,
				"sequence": sequence,
				"reviewer_user": reviewer_user,
				"reviewer_label": reviewer_user,
				"is_required": is_required,
			}
		)
		step.insert(ignore_permissions=True)
		return step

	def _single_reviewer_submission(self, reviewer_user):
		"""One stage, one required reviewer, nothing planned after it — the base case forwarding
		is designed for."""
		doc = self._make_document(f"DOC-{frappe.generate_hash(length=6)}")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal(f"SUB-{frappe.generate_hash(length=6)}")
		submission = self._make_draft_submission(submittal.name, "00", [rev.name])
		step = self._add_step(submission.name, 0, reviewer_user)
		submission.submit()
		return submission, step

	# -- positive path -------------------------------------------------------------------------

	def test_forward_creates_new_step_and_moves_ball_in_court(self):
		submission, step = self._single_reviewer_submission(self.user_a)

		submittal_control.record_step_response(step.name, c.RESPONSE_APPROVED, forward_to_user=self.user_b)

		old = frappe.get_doc("EGC Submittal Review Step", step.name)
		self.assertEqual(old.status, c.STEP_RESPONDED)

		new_steps = frappe.get_all(
			"EGC Submittal Review Step",
			filters={"submittal_revision": submission.name, "reviewer_user": self.user_b},
			fields=["name", "status", "origin", "sequence", "is_required"],
		)
		self.assertEqual(len(new_steps), 1)
		self.assertEqual(new_steps[0].status, c.STEP_IN_REVIEW)
		self.assertEqual(new_steps[0].origin, "Forwarded")
		self.assertGreater(new_steps[0].sequence, old.sequence)

		submittal = frappe.get_doc("EGC Submittal", submission.submittal)
		expected_label = frappe.db.get_value("User", self.user_b, "full_name")
		self.assertIn(expected_label, submittal.ball_in_court or "")

	def test_chain_terminates_normally_with_no_forward(self):
		submission, step = self._single_reviewer_submission(self.user_a)
		submittal_control.record_step_response(step.name, c.RESPONSE_APPROVED)

		submission.reload()
		self.assertEqual(submission.submission_status, c.SUBMISSION_RESPONDED)
		self.assertEqual(submission.response, c.RESPONSE_APPROVED)
		self.assertFalse(
			frappe.get_all("EGC Submittal Review Step", filters={"submittal_revision": submission.name, "status": c.STEP_IN_REVIEW})
		)

	def test_forward_chain_ends_when_final_response_has_no_forward(self):
		submission, step_a = self._single_reviewer_submission(self.user_a)
		submittal_control.record_step_response(step_a.name, c.RESPONSE_APPROVED, forward_to_user=self.user_b)

		step_b = frappe.get_all(
			"EGC Submittal Review Step", filters={"submittal_revision": submission.name, "reviewer_user": self.user_b}, pluck="name"
		)[0]
		submittal_control.record_step_response(step_b, c.RESPONSE_APPROVED)

		submission.reload()
		self.assertEqual(submission.submission_status, c.SUBMISSION_RESPONDED)
		self.assertEqual(submission.response, c.RESPONSE_APPROVED)

	# -- terminal responses never forward -------------------------------------------------------

	def test_terminal_response_rejects_a_supplied_forward_target(self):
		submission, step = self._single_reviewer_submission(self.user_a)
		with self.assertRaises(frappe.ValidationError):
			submittal_control.record_step_response(step.name, c.RESPONSE_REJECTED, forward_to_user=self.user_b)

	def test_revise_and_resubmit_rejects_a_supplied_forward_target(self):
		submission, step = self._single_reviewer_submission(self.user_a)
		with self.assertRaises(frappe.ValidationError):
			submittal_control.record_step_response(step.name, c.RESPONSE_REVISE_AND_RESUBMIT, forward_to_user=self.user_b, remarks="fix it")

	# -- multi-reviewer stage: forwarding rejected server-side, not silently offered -------------

	def test_multi_reviewer_stage_rejects_forwarding(self):
		doc = self._make_document("DOC-FWD-MULTI")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-FWD-MULTI")
		submission = self._make_draft_submission(submittal.name, "00", [rev.name])
		step_a = self._add_step(submission.name, 0, self.user_a)
		self._add_step(submission.name, 0, self.user_b)
		submission.submit()

		with self.assertRaises(frappe.ValidationError):
			submittal_control.record_step_response(step_a.name, c.RESPONSE_APPROVED, forward_to_user=self.user_c)

	# -- self-forward rejected -------------------------------------------------------------------

	def test_self_forward_rejected(self):
		submission, step = self._single_reviewer_submission(self.user_a)
		frappe.set_user(self.user_a)
		with self.assertRaises(frappe.ValidationError):
			submittal_control.record_step_response(step.name, c.RESPONSE_APPROVED, forward_to_user=self.user_a)

	# -- bypassing a pre-planned stage: it's Skipped, and it never resurfaces --------------------

	def test_forward_past_a_pre_planned_stage_skips_it_permanently(self):
		doc = self._make_document("DOC-FWD-SKIP")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-FWD-SKIP")
		submission = self._make_draft_submission(submittal.name, "00", [rev.name])
		step_a = self._add_step(submission.name, 0, self.user_a)
		# Pre-planned stage 2, for user_b — this is the one that must be bypassed and Skipped.
		self._add_step(submission.name, 1, self.user_b)
		submission.submit()

		# Forward to user_c instead of the pre-planned user_b.
		submittal_control.record_step_response(step_a.name, c.RESPONSE_APPROVED, forward_to_user=self.user_c)

		pre_planned = frappe.get_doc("EGC Submittal Review Step", frappe.get_all(
			"EGC Submittal Review Step", filters={"submittal_revision": submission.name, "reviewer_user": self.user_b}, pluck="name"
		)[0])
		self.assertEqual(pre_planned.status, c.STEP_SKIPPED)

		# The forwarded step (user_c) responds — the orphaned Skipped row must never reopen.
		step_c = frappe.get_all(
			"EGC Submittal Review Step", filters={"submittal_revision": submission.name, "reviewer_user": self.user_c}, pluck="name"
		)[0]
		submittal_control.record_step_response(step_c, c.RESPONSE_APPROVED)

		pre_planned.reload()
		self.assertEqual(pre_planned.status, c.STEP_SKIPPED)
		submission.reload()
		self.assertEqual(submission.submission_status, c.SUBMISSION_RESPONDED)

	# -- forwarding to exactly the pre-planned reviewer doesn't duplicate -------------------------

	def test_forward_to_pre_planned_reviewer_does_not_duplicate(self):
		doc = self._make_document("DOC-FWD-DEDUPE")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("SUB-FWD-DEDUPE")
		submission = self._make_draft_submission(submittal.name, "00", [rev.name])
		step_a = self._add_step(submission.name, 0, self.user_a)
		self._add_step(submission.name, 1, self.user_b)
		submission.submit()

		submittal_control.record_step_response(step_a.name, c.RESPONSE_APPROVED, forward_to_user=self.user_b)

		rows = frappe.get_all("EGC Submittal Review Step", filters={"submittal_revision": submission.name, "reviewer_user": self.user_b})
		self.assertEqual(len(rows), 1)

	# -- external reviewer can forward without a PermissionError -----------------------------------

	def test_external_reviewer_can_forward_without_permission_error(self):
		submission, step = self._single_reviewer_submission(self.external_user)
		frappe.set_user(self.external_user)
		# Must not raise — EGC External Viewer has no `create` on EGC Submittal Review Step, so
		# the forward-insert must use ignore_permissions=True internally.
		submittal_control.record_step_response(step.name, c.RESPONSE_APPROVED, forward_to_user=self.user_b)

		frappe.set_user("Administrator")
		new_steps = frappe.get_all("EGC Submittal Review Step", filters={"submittal_revision": submission.name, "reviewer_user": self.user_b})
		self.assertEqual(len(new_steps), 1)

	# -- forwarding back to someone who already responded earlier this cycle ----------------------

	def test_forward_to_a_prior_responder_creates_a_fresh_step(self):
		submission, step_a = self._single_reviewer_submission(self.user_a)
		submittal_control.record_step_response(step_a.name, c.RESPONSE_APPROVED, forward_to_user=self.user_b)

		step_b = frappe.get_all(
			"EGC Submittal Review Step", filters={"submittal_revision": submission.name, "reviewer_user": self.user_b}, pluck="name"
		)[0]
		submittal_control.record_step_response(step_b, c.RESPONSE_APPROVED, forward_to_user=self.user_a)

		a_steps = frappe.get_all(
			"EGC Submittal Review Step", filters={"submittal_revision": submission.name, "reviewer_user": self.user_a}, fields=["name", "status"]
		)
		self.assertEqual(len(a_steps), 2)
		statuses = sorted(row.status for row in a_steps)
		self.assertEqual(statuses, [c.STEP_IN_REVIEW, c.STEP_RESPONDED])
