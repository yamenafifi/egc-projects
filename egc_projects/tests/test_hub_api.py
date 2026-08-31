# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Tests for `api/hub.py` — docs/ARCHITECTURE.md §5 (contract), §4 (permissions), §6 (financials).

Fixture style matches `test_document_control.py` exactly: one shared set of masters in
`setUpClass`, one dedicated `Project` per test in `setUp`, private `.txt` File fixtures (a
fabricated `.pdf` body fails Frappe's PDF content scan on insert).

EGC roles are additive and grant nothing on core `Project` (docs/ARCHITECTURE.md §4), so every
non-Administrator test user is built with a standard ERPNext `Projects User` role in addition to
whatever EGC role is under test — otherwise every endpoint would fail at the `Project` read gate
before ever reaching the behaviour being tested.
"""

import frappe
from frappe.permissions import add_user_permission
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from egc_projects.api import hub
from egc_projects.egc_projects import constants as c
from egc_projects.egc_projects import submittal_control
from egc_projects.egc_projects.report.egc_activity_status_summary import egc_activity_status_summary
from egc_projects.egc_projects.report.egc_drawing_register import egc_drawing_register
from egc_projects.egc_projects.report.egc_submittal_log import egc_submittal_log

#: The seven `project`-first endpoints in the stable Hub contract (docs/ARCHITECTURE.md §5).
#: `get_document_revisions` is deliberately excluded — it gates on a `document`, not a `project`,
#: and is covered separately.
_HUB_PROJECT_ENDPOINTS = (
	"get_project_context",
	"get_overview",
	"get_wbs_tree",
	"get_activities",
	"get_submittals",
	"get_drawings",
	"get_financials",
)


class TestHubAPI(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")

		cls.company = frappe.db.get_value("Company", {}, "name") or frappe.get_all(
			"Company", limit=1, pluck="name"
		)[0]
		cls.document_type = _get_or_create_document_type()
		cls.drawing_type = _get_or_create_drawing_type()
		cls.discipline = _get_or_create_discipline()
		cls.submittal_type = _get_or_create_submittal_type()

		# A stable project the fenced-out user IS allowed to see. A `User Permission` on
		# `Project` restricted to this decoy means every project a test creates in `setUp` is,
		# by construction, outside what that user can read.
		cls.decoy_project = _make_project(cls.company)

		cls.manager_user = _get_or_create_user(
			"egc-hub-manager@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		# Passes the `Project` read gate (`Projects User`) but holds no financial role — the
		# financial gate, not the project gate, is what must reject this user.
		cls.financial_denied_user = _get_or_create_user(
			"egc-hub-viewer@example.com", ["Projects User", c.ROLE_PROJECT_VIEWER]
		)
		# Holds every role that would normally grant access, but is fenced to `decoy_project` —
		# proves the Hub cannot be bypassed by role alone once User Permissions are in play.
		cls.project_denied_user = _get_or_create_user(
			"egc-hub-fenced@example.com", ["Projects User", c.ROLE_PROJECT_MANAGER]
		)
		add_user_permission("Project", cls.decoy_project, cls.project_denied_user, ignore_permissions=True)

	def setUp(self):
		self.project = _make_project(self.company)

	def tearDown(self):
		# Every test that switches `frappe.session.user` must restore Administrator, even if the
		# test body raised — unittest always runs tearDown after a failed test, so this is
		# unconditional rather than wrapped in the test methods themselves.
		frappe.set_user("Administrator")

	def test_undated_records_are_not_counted_overdue(self):
		"""A record with no date is not overdue — the aggregate must agree with is_overdue().

		Regression test. Frappe rewrites a `<` filter on a nullable field as
		`IFNULL(field, '') < value`, so before the guard in `_activity_overview` /
		`_submittal_overview` an activity or submittal with no date compared `'' < today()`
		and was silently counted as overdue.
		"""
		self._make_activity("OD-NODATE", status=c.ACTIVITY_ON_HOLD)
		self._make_activity(
			"OD-REAL", status=c.ACTIVITY_IN_PROGRESS, planned_end_date=add_days(today(), -3)
		)

		overview = hub.get_overview(self.project)
		self.assertEqual(overview["activities"]["overdue"], 1)

		submittal = self._make_submittal("SUB-NODATE")
		self.assertFalse(frappe.db.get_value("EGC Submittal", submittal.name, "current_due_date"))
		self.assertEqual(hub.get_overview(self.project)["submittals"]["overdue"], 0)

	# -- fixtures ------------------------------------------------------------------------------

	def _make_activity(self, code, status=c.ACTIVITY_NOT_STARTED, **kwargs):
		values = {
			"doctype": "EGC Activity",
			"project": self.project,
			"activity_code": code,
			"activity_name": kwargs.pop("activity_name", code),
			"status": status,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_assignment(self, parent_doctype, parent_name, person, assignment_role="Responsible"):
		doc = frappe.get_doc(
			{
				"doctype": "EGC Assignment",
				"parent_doctype": parent_doctype,
				"parent_name": parent_name,
				"person": person,
				"assignment_role": assignment_role,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	def _make_document(self, document_number="DOC-001", document_type=None, **kwargs):
		values = {
			"doctype": "EGC Project Document",
			"project": self.project,
			"document_number": document_number,
			"title": kwargs.pop("title", document_number),
			"document_type": document_type or self.document_type,
			"discipline": self.discipline,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def _make_issued_revision(self, document, revision, **kwargs):
		values = {
			"doctype": "EGC Project Document Revision",
			"document": document,
			"revision": revision,
			"file": _make_private_file(),
			"revision_date": today(),
		}
		values.update(kwargs)
		rev = frappe.get_doc(values)
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

	def _make_submission(self, submittal, revision_label, document_revisions=None, **kwargs):
		values = {
			"doctype": "EGC Submittal Revision",
			"submittal": submittal,
			"revision_label": revision_label,
			"date_submitted": today(),
		}
		values.update(kwargs)
		sub = frappe.get_doc(values)
		for rev_name in document_revisions or []:
			sub.append("documents", {"document_revision": rev_name})
		sub.insert(ignore_permissions=True)
		return sub

	def _make_responded_submittal(self, number, response, issued_revision, due_date=None):
		submittal = self._make_submittal(number)
		sub = self._make_submission(
			submittal.name, "00", document_revisions=[issued_revision.name], due_date=due_date
		)
		sub.submit()
		submittal_control.record_response(sub.name, response)
		return submittal

	# -- 1. Overview counts ----------------------------------------------------------------

	def test_overview_counts_exact(self):
		# Activities: one of each tracked status, plus a specific overdue/not-overdue pair —
		# `Completed` with a past planned finish must NOT count as overdue (derived rule,
		# docs/ARCHITECTURE.md §2.3: closed statuses are never overdue regardless of date).
		# NOTE: every activity here carries an explicit `planned_end_date`, deliberately never
		# `None`. `hub._activity_overview()`'s overdue COUNT uses a raw `frappe.get_all` "<"
		# filter, which `frappe.db` rewrites as `IFNULL(planned_end_date, '') < today()` — so a
		# genuinely unset date collapses to `'' < today()`, which is TRUE, and gets miscounted as
		# overdue. This is a real defect (reported separately, not fixed here — see the test
		# module's docstring / report); this fixture avoids it so the test asserts the *intended*
		# semantics without baking the bug's wrong answer into the expected counts.
		self._make_activity("OV-A1", c.ACTIVITY_IN_PROGRESS, planned_end_date=add_days(today(), -3))
		self._make_activity("OV-A2", c.ACTIVITY_COMPLETED, planned_end_date=add_days(today(), -3))
		self._make_activity("OV-A3", c.ACTIVITY_NOT_STARTED, planned_end_date=add_days(today(), 10))
		self._make_activity("OV-A4", c.ACTIVITY_ON_HOLD, planned_end_date=add_days(today(), 10))

		# One issued drawing (Not Submitted) and one issued drawing under review, so both
		# `issued` and `pending_review` are exercised.
		drawing_ok = self._make_document("OV-DRW-001", document_type=self.drawing_type)
		self._make_issued_revision(drawing_ok.name, "00")

		drawing_under_review = self._make_document("OV-DRW-002", document_type=self.drawing_type)
		review_rev = self._make_issued_revision(drawing_under_review.name, "00")
		review_submittal = self._make_submittal("OV-DRW-SUB")
		# `due_date` deliberately in the future, not `None` — see the note above `OV-A4`; the
		# same `IFNULL` rewrite affects `_submittal_overview`'s `current_due_date < today()`
		# overdue count.
		review_submission = self._make_submission(
			review_submittal.name,
			"00",
			document_revisions=[review_rev.name],
			due_date=add_days(today(), 10),
		)
		review_submission.submit()  # left Submitted, no response yet -> document Under Review

		# Submittals: a distinct issued revision per responded submittal (Approved / Approved
		# with Comments / Revise & Resubmit / Rejected) plus one more for the overdue open
		# submission — a document revision can only be under review through one submittal at a
		# time (egc_submittal_revision.py's own `_validate_documents()`), so each of these five
		# needs its own document even though this test only cares about the aggregate counts.
		def _make_reviewed_revision(suffix):
			doc = self._make_document(f"OV-SUB-DOC-{suffix}")
			return self._make_issued_revision(doc.name, "00")

		self._make_responded_submittal("OV-SUB-APPR", c.RESPONSE_APPROVED, _make_reviewed_revision("APPR"))
		self._make_responded_submittal(
			"OV-SUB-AWC", c.RESPONSE_APPROVED_WITH_COMMENTS, _make_reviewed_revision("AWC")
		)
		self._make_responded_submittal(
			"OV-SUB-REV", c.RESPONSE_REVISE_AND_RESUBMIT, _make_reviewed_revision("REV")
		)
		self._make_responded_submittal("OV-SUB-REJ", c.RESPONSE_REJECTED, _make_reviewed_revision("REJ"))

		overdue_submittal = self._make_submittal("OV-SUB-OVERDUE")
		overdue_submission = self._make_submission(
			overdue_submittal.name,
			"00",
			document_revisions=[_make_reviewed_revision("OVERDUE").name],
			due_date=add_days(today(), -2),
		)
		overdue_submission.submit()

		overview = hub.get_overview(self.project)

		self.assertEqual(
			overview["activities"],
			{"total": 4, "completed": 1, "in_progress": 1, "not_started": 1, "overdue": 1},
		)
		self.assertEqual(
			overview["submittals"],
			{
				"total": 6,
				"approved": 1,
				"approved_with_comments": 1,
				"under_review": 2,  # review_submission + overdue_submission, both still "Submitted"
				"revise_resubmit": 1,
				"rejected": 1,
				"overdue": 1,  # only overdue_submission has a past due date
			},
		)
		self.assertEqual(
			overview["drawings"],
			{"total": 2, "issued": 2, "pending_review": 1, "approved": 0},
		)

	# -- 2. Financials are a pure passthrough of `tabProject` -------------------------------

	def test_financials_equal_raw_project_fields(self):
		raw_values = {
			"total_billed_amount": 125000.5,
			"total_purchase_cost": 42000.25,
			"total_consumed_material_cost": 15000,
			"total_costing_amount": 8000,
			"total_billable_amount": 9000,
			"total_sales_amount": 200000,
			"gross_margin": 60000,
			"per_gross_margin": 30,
		}
		frappe.db.set_value("Project", self.project, raw_values)

		frappe.set_user(self.manager_user)
		result = hub.get_financials(self.project)

		# The point of this test: `get_financials` must be a pure passthrough of `tabProject`
		# fields written by ERPNext/HRMS controllers, never a re-aggregation of Sales/Purchase
		# Invoices, Timesheets or Stock Entries (docs/ARCHITECTURE.md §6). Writing arbitrary
		# values directly to the Project row and asserting the API echoes back exactly those
		# values (read a second time, independently, via `frappe.db.get_value`) is what proves
		# no second computation is happening in between.
		self.assertEqual(
			result["billed"], frappe.db.get_value("Project", self.project, "total_billed_amount")
		)
		self.assertEqual(
			result["purchase_cost"], frappe.db.get_value("Project", self.project, "total_purchase_cost")
		)
		self.assertEqual(
			result["consumed_material_cost"],
			frappe.db.get_value("Project", self.project, "total_consumed_material_cost"),
		)
		self.assertEqual(
			result["timesheet_cost"], frappe.db.get_value("Project", self.project, "total_costing_amount")
		)
		self.assertEqual(
			result["billable"], frappe.db.get_value("Project", self.project, "total_billable_amount")
		)
		self.assertEqual(
			result["sales_order_value"], frappe.db.get_value("Project", self.project, "total_sales_amount")
		)
		self.assertEqual(result["gross_margin"], frappe.db.get_value("Project", self.project, "gross_margin"))
		self.assertEqual(
			result["per_gross_margin"], frappe.db.get_value("Project", self.project, "per_gross_margin")
		)
		# And those raw values are exactly what this test wrote, not some other derived figure.
		for key, field in (
			("billed", "total_billed_amount"),
			("purchase_cost", "total_purchase_cost"),
			("consumed_material_cost", "total_consumed_material_cost"),
			("timesheet_cost", "total_costing_amount"),
			("billable", "total_billable_amount"),
			("sales_order_value", "total_sales_amount"),
			("gross_margin", "gross_margin"),
			("per_gross_margin", "per_gross_margin"),
		):
			self.assertEqual(result[key], raw_values[field])

	# -- 3. Financial gate --------------------------------------------------------------------

	def test_financial_gate_denies_viewer_and_allows_manager(self):
		frappe.set_user(self.financial_denied_user)
		with self.assertRaises(frappe.PermissionError):
			hub.get_financials(self.project)
		# The project gate alone must still let this user through to non-financial data.
		overview = hub.get_overview(self.project)
		self.assertFalse(hub.get_project_context(self.project)["permissions"]["financials"])
		# Regression: get_overview()'s own "financials" health dot used to leak a red/green
		# signal derived from gross_margin — a commercial figure — to anyone who could merely
		# open the Overview tab, even though get_financials() itself correctly refuses them.
		self.assertNotIn("financials", overview["health"])

		frappe.set_user(self.manager_user)
		hub.get_financials(self.project)  # must not raise
		self.assertTrue(hub.get_project_context(self.project)["permissions"]["financials"])
		self.assertIn("financials", hub.get_overview(self.project)["health"])

	# -- 4. Project isolation via the API ------------------------------------------------------

	def test_project_isolation_denies_every_endpoint(self):
		frappe.set_user(self.project_denied_user)
		for name in _HUB_PROJECT_ENDPOINTS:
			endpoint = getattr(hub, name)
			with self.subTest(endpoint=name):
				with self.assertRaises(frappe.PermissionError):
					endpoint(self.project)

	# -- 5. Filter allow-list -------------------------------------------------------------------

	def test_activities_filter_allow_list(self):
		self._make_activity("FLT-A1", c.ACTIVITY_COMPLETED)
		self._make_activity("FLT-A2", c.ACTIVITY_NOT_STARTED)

		with self.assertRaises(frappe.ValidationError):
			hub.get_activities(self.project, {"owner": "x"})
		with self.assertRaises(frappe.ValidationError):
			hub.get_activities(self.project, {"1=1": "x"})

		rows = hub.get_activities(self.project, {"status": c.ACTIVITY_COMPLETED})
		self.assertEqual({row.activity_code for row in rows}, {"FLT-A1"})

	def test_submittals_filter_allow_list(self):
		doc = self._make_document("FLT-SUB-DOC")
		rev = self._make_issued_revision(doc.name, "00")
		self._make_responded_submittal("FLT-SUB-APPR", c.RESPONSE_APPROVED, rev)
		other = self._make_submittal("FLT-SUB-DRAFT")

		with self.assertRaises(frappe.ValidationError):
			hub.get_submittals(self.project, {"owner": "x"})
		with self.assertRaises(frappe.ValidationError):
			hub.get_submittals(self.project, {"1=1": "x"})

		rows = hub.get_submittals(self.project, {"submittal_status": c.RESPONSE_APPROVED})
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].submittal_number, "FLT-SUB-APPR")
		self.assertNotIn(other.name, [row.name for row in rows])

	def test_drawings_filter_allow_list(self):
		drawing = self._make_document("FLT-DRW-001", document_type=self.drawing_type)
		self._make_issued_revision(drawing.name, "00")

		with self.assertRaises(frappe.ValidationError):
			hub.get_drawings(self.project, {"owner": "x"})
		with self.assertRaises(frappe.ValidationError):
			hub.get_drawings(self.project, {"1=1": "x"})

		rows = hub.get_drawings(self.project, {"discipline": self.discipline})
		self.assertEqual({row.number for row in rows}, {"FLT-DRW-001"})

	# -- 6. get_document_revisions ---------------------------------------------------------------

	def test_document_revisions_newest_first_current_identifiable_and_gated(self):
		doc = self._make_document("REV-DOC")
		self._make_issued_revision(doc.name, "00")
		self._make_issued_revision(doc.name, "01")  # supersedes 00

		rows = hub.get_document_revisions(doc.name)

		self.assertEqual([row.revision for row in rows], ["01", "00"])
		self.assertGreater(rows[0].revision_seq, rows[1].revision_seq)
		self.assertEqual(rows[0].revision_status, c.REVISION_ISSUED)
		self.assertEqual(rows[0].docstatus, 1)
		self.assertEqual(rows[1].revision_status, c.REVISION_SUPERSEDED)

		frappe.set_user(self.project_denied_user)
		with self.assertRaises(frappe.PermissionError):
			hub.get_document_revisions(doc.name)

	# -- 7. Reports -------------------------------------------------------------------------------

	def test_drawing_register_report(self):
		drawing = self._make_document("RPT-DRW-001", document_type=self.drawing_type)
		self._make_issued_revision(drawing.name, "00")

		columns, rows = egc_drawing_register.execute({"project": self.project})
		self.assertTrue(columns)
		self.assertEqual([row["document_number"] for row in rows], ["RPT-DRW-001"])
		self.assertEqual(rows[0]["current_revision_label"], "00")

		with self.assertRaises(frappe.ValidationError):
			egc_drawing_register.execute({})

	def test_submittal_log_report(self):
		doc = self._make_document("RPT-SUB-DOC")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("RPT-SUB-001")
		sub = self._make_submission(submittal.name, "00", document_revisions=[rev.name])
		sub.submit()

		columns, rows = egc_submittal_log.execute({"project": self.project})
		self.assertTrue(columns)
		self.assertEqual([row["submittal_number"] for row in rows], ["RPT-SUB-001"])

		with self.assertRaises(frappe.ValidationError):
			egc_submittal_log.execute({})

	def test_activity_status_summary_indent_reflects_tree_depth(self):
		root = self._make_activity("RPT-ROOT", is_group=1)
		mid = self._make_activity("RPT-MID", is_group=1, parent_egc_activity=root.name)
		self._make_activity("RPT-LEAF", parent_egc_activity=mid.name)

		columns, rows = egc_activity_status_summary.execute({"project": self.project})
		self.assertTrue(columns)

		indent_by_code = {row["activity_code"]: row["indent"] for row in rows}
		self.assertEqual(indent_by_code["RPT-ROOT"], 0)
		self.assertEqual(indent_by_code["RPT-MID"], 1)
		self.assertEqual(indent_by_code["RPT-LEAF"], 2)

		with self.assertRaises(frappe.ValidationError):
			egc_activity_status_summary.execute({})

	# -- Project health (docs/ARCHITECTURE_V2.md §11) -------------------------------------------

	def _make_review_step(self, submission, **kwargs):
		values = {
			"doctype": "EGC Submittal Review Step",
			"submittal_revision": submission,
			"sequence": 0,
			"status": "In Review",
			"reviewer_user": self.manager_user,
		}
		values.update(kwargs)
		doc = frappe.get_doc(values)
		doc.insert(ignore_permissions=True)
		return doc

	def test_project_health_all_green_on_empty_project(self):
		self.assertEqual(
			hub.get_overview(self.project)["health"],
			{"schedule": "green", "submittals": "green", "documents": "green", "financials": "green"},
		)

	def test_schedule_health_red_then_orange_once_touched(self):
		overdue = self._make_activity(
			"HLT-SCH-1", c.ACTIVITY_IN_PROGRESS, planned_end_date=add_days(today(), -20)
		)
		# A freshly-inserted row's own `modified` is "now" by construction, so the "touched
		# recently" check would trivially pass — backdate it past the 14-day window first to
		# reach the actual "red" (stale, never touched) state the rule describes.
		frappe.db.set_value(
			"EGC Activity", overdue.name, "modified", add_days(today(), -20), update_modified=False
		)
		self.assertEqual(hub.get_overview(self.project)["health"]["schedule"], "red")

		# Touching the row (any save) within the last 14 days flips red -> orange, not green —
		# the Activity is still overdue, it is just no longer being ignored.
		overdue.reload()
		overdue.description = "checked in on this today"
		overdue.save(ignore_permissions=True)
		self.assertEqual(hub.get_overview(self.project)["health"]["schedule"], "orange")

	def test_schedule_health_ignores_closed_and_undated_activities(self):
		self._make_activity(
			"HLT-SCH-DONE", c.ACTIVITY_COMPLETED, planned_end_date=add_days(today(), -20)
		)
		self._make_activity("HLT-SCH-NODATE", c.ACTIVITY_IN_PROGRESS)
		self.assertEqual(hub.get_overview(self.project)["health"]["schedule"], "green")

	def test_submittals_health_red_overdue_beats_orange_needs_resubmit(self):
		# Two distinct documents — a document revision can only be under review through one
		# submittal at a time (egc_submittal_revision.py's own `_validate_documents()`), so the
		# Revise & Resubmit submittal and the overdue submittal cannot share one revision.
		rnr_doc = self._make_document("HLT-SUB-DOC-RNR")
		rnr_rev = self._make_issued_revision(rnr_doc.name, "00")
		self._make_responded_submittal("HLT-SUB-RNR", c.RESPONSE_REVISE_AND_RESUBMIT, rnr_rev)
		self.assertEqual(hub.get_overview(self.project)["health"]["submittals"], "orange")

		overdue_doc = self._make_document("HLT-SUB-DOC-OVERDUE")
		overdue_rev = self._make_issued_revision(overdue_doc.name, "00")
		overdue_submittal = self._make_submittal("HLT-SUB-OVERDUE")
		overdue_submission = self._make_submission(
			overdue_submittal.name, "00", document_revisions=[overdue_rev.name], due_date=add_days(today(), -5)
		)
		overdue_submission.submit()
		self.assertEqual(hub.get_overview(self.project)["health"]["submittals"], "red")

	def test_drawings_health_orange_only_past_the_governing_submittals_due_date(self):
		drawing = self._make_document("HLT-DRW-001", document_type=self.drawing_type)
		rev = self._make_issued_revision(drawing.name, "00")
		submittal = self._make_submittal("HLT-DRW-SUB")

		future_submission = self._make_submission(
			submittal.name, "00", document_revisions=[rev.name], due_date=add_days(today(), 10)
		)
		future_submission.submit()  # Submitted, no response -> drawing approval_status = Under Review
		self.assertEqual(hub.get_overview(self.project)["health"]["documents"], "green")

		# Move the SAME governing submission's due date into the past — the drawing's own
		# approval_status doesn't change, only whether it is now considered late.
		frappe.db.set_value("EGC Submittal Revision", future_submission.name, "due_date", add_days(today(), -3))
		self.assertEqual(hub.get_overview(self.project)["health"]["documents"], "orange")

	def test_drawings_health_batches_across_multiple_at_risk_drawings_correctly(self):
		"""Regression: `_governing_submission_due_dates` fetches every at-risk drawing's governing
		due date in ONE batched query, grouped by `document_revision` — this pins that the
		grouping never mixes up one drawing's due date with another's. Two at-risk drawings, only
		one genuinely overdue: overall health must still read "orange" (not "green", which a
		broken grouping that only kept the wrong revision's date could produce), and flipping the
		overdue one back to green must be independently detectable."""
		on_time_drawing = self._make_document("HLT-DRW-BATCH-1", document_type=self.drawing_type)
		on_time_rev = self._make_issued_revision(on_time_drawing.name, "00")
		on_time_submittal = self._make_submittal("HLT-DRW-BATCH-SUB-1")
		on_time_submission = self._make_submission(
			on_time_submittal.name, "00", document_revisions=[on_time_rev.name], due_date=add_days(today(), 10)
		)
		on_time_submission.submit()

		late_drawing = self._make_document("HLT-DRW-BATCH-2", document_type=self.drawing_type)
		late_rev = self._make_issued_revision(late_drawing.name, "00")
		late_submittal = self._make_submittal("HLT-DRW-BATCH-SUB-2")
		late_submission = self._make_submission(
			late_submittal.name, "00", document_revisions=[late_rev.name], due_date=add_days(today(), -3)
		)
		late_submission.submit()

		self.assertEqual(hub.get_overview(self.project)["health"]["documents"], "orange")

		# Bringing the late one current again must flip the overall signal back to green — proof
		# the two drawings' due dates were never conflated with each other.
		frappe.db.set_value("EGC Submittal Revision", late_submission.name, "due_date", add_days(today(), 10))
		self.assertEqual(hub.get_overview(self.project)["health"]["documents"], "green")

	def test_financials_health_red_when_gross_margin_negative(self):
		frappe.db.set_value("Project", self.project, "gross_margin", -500)
		self.assertEqual(hub.get_overview(self.project)["health"]["financials"], "red")
		frappe.db.set_value("Project", self.project, "gross_margin", 500)
		self.assertEqual(hub.get_overview(self.project)["health"]["financials"], "green")

	# -- My Open Items (docs/ARCHITECTURE_V2.md §8) ----------------------------------------------

	def test_my_open_items_combines_submittal_review_and_overdue_activity(self):
		doc = self._make_document("OPEN-DOC")
		rev = self._make_issued_revision(doc.name, "00")
		submittal = self._make_submittal("OPEN-SUB-001", submittal_manager=self.manager_user)
		submission = self._make_submission(submittal.name, "00", document_revisions=[rev.name])
		submission.submit()
		self._make_review_step(submission.name)

		overdue_activity = self._make_activity(
			"OPEN-ACT-001", c.ACTIVITY_IN_PROGRESS, planned_end_date=add_days(today(), -2)
		)
		# Not overdue, not returned — proves the activity source filters by is_overdue(), not
		# merely by being assigned.
		not_overdue_activity = self._make_activity(
			"OPEN-ACT-002", c.ACTIVITY_IN_PROGRESS, planned_end_date=add_days(today(), 10)
		)
		# `person` links directly to a User now — no separate identity record to create first.
		self._make_assignment("EGC Activity", overdue_activity.name, self.manager_user)
		self._make_assignment("EGC Activity", not_overdue_activity.name, self.manager_user)

		frappe.set_user(self.manager_user)
		items = hub.get_my_open_items(self.project)

		self.assertEqual({(i["source"], i["name"]) for i in items}, {
			("submittal_review", submittal.name),
			("activity_overdue", overdue_activity.name),
		})
		self.assertTrue(all(i["project"] == self.project for i in items))

	def test_my_open_items_project_isolation(self):
		frappe.set_user(self.project_denied_user)
		with self.assertRaises(frappe.PermissionError):
			hub.get_my_open_items(self.project)
		# No `project` filter at all must not raise — it is a scope, not a gate; permission is
		# still per-item via `get_open_items_for_user`'s own project membership.
		self.assertEqual(hub.get_my_open_items(), [])


def _get_or_create_document_type():
	name = "EGC-HUB-Test Document Type"
	if frappe.db.exists("EGC Document Type", name):
		return name
	frappe.get_doc(
		{
			"doctype": "EGC Document Type",
			"document_type_name": name,
			"abbreviation": "TST",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return name


def _get_or_create_drawing_type():
	name = "EGC-HUB-Test Drawing Type"
	if frappe.db.exists("EGC Document Type", name):
		return name
	frappe.get_doc(
		{
			"doctype": "EGC Document Type",
			"document_type_name": name,
			"abbreviation": "DRW",
			"is_drawing": 1,
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return name


def _get_or_create_discipline():
	code = "ZZHB"
	if frappe.db.exists("EGC Discipline", code):
		return code
	frappe.get_doc(
		{
			"doctype": "EGC Discipline",
			"discipline_code": code,
			"discipline_name": "EGC-HUB-Test Discipline",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return code


def _get_or_create_submittal_type():
	name = "EGC-HUB-Test Submittal Type"
	if frappe.db.exists("EGC Submittal Type", name):
		return name
	frappe.get_doc(
		{
			"doctype": "EGC Submittal Type",
			"submittal_type_name": name,
			"abbreviation": "TST",
			"enabled": 1,
		}
	).insert(ignore_permissions=True)
	return name


def _get_or_create_user(email, roles):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
			}
		)
		user.insert(ignore_permissions=True)
	user.add_roles(*roles)
	return user.name


def _make_project(company):
	doc = frappe.get_doc(
		{
			"doctype": "Project",
			"project_name": f"EGC-HUB-Test-{frappe.generate_hash(length=8)}",
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _make_private_file():
	# Plain text, not .pdf: a fabricated PDF body fails Frappe's PDF malware/JS content scan on
	# insert. The controlled-document fields don't care about content, only that it's a real,
	# private File record with a real file_url.
	token = frappe.generate_hash(length=8)
	doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{token}.txt",
			"content": f"test hub api content {token}".encode(),
			"is_private": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.file_url
