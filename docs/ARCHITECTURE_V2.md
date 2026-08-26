# EGC Projects — v2 Architecture Addendum (Functional Depth & Hub UX Upgrade)

This is a binding addendum to `docs/ARCHITECTURE.md`, written after a live audit of the running
v1 application. It does not replace v1's architecture — it extends it, and calls out every place
it deliberately revises a v1 decision, with the reasoning, as required by the upgrade brief.

`docs/ARCHITECTURE.md` remains authoritative for everything it covers that this document does
not touch (naming, revision integrity, permissions model, financials-read-only rule, etc).

---

## 0. Live audit findings (what this upgrade fixes)

Confirmed in the browser against the running v1 Hub, not inferred from source:

1. **Every list row exits the Hub.** Clicking a Submittal, Activity, or Drawing row drops the
   user onto the raw Frappe DocType form — no workflow visualization, no related-record panel
   beyond a bare "Linked Documents & Submittals" list, no actions beyond native Save.
2. **No creation flow lives in the Hub.** There is no "+ New Submittal" anywhere in the Hub;
   the only way to create one is the native Frappe "New" form.
3. **Overview is KPI cards only.** No parties, no stage, no "what needs my attention right
   now," no quick actions, no project health.
4. **Documents has no home.** `EGC Project Document` only surfaces through the Drawings filter
   (`document_type.is_drawing=1`); a non-drawing controlled document (spec, method statement,
   calculation) has no register at all in the Hub.
5. **Activities are a flat table.** No hierarchy indentation in the Hub grid, no schedule depth
   (actual/forecast dates, duration, milestone), no dependencies, no Gantt, no parent rollup —
   a group Activity is a manually-edited row unrelated to its children.
6. **Submittals are single-response.** One `record_response()` call terminates the cycle; there
   is no multi-step review, no Ball in Court, no notification on state change.
7. **Drawings have no Set/Area grouping** and no controlled pre-issue state — a revision is
   either a bare Draft or fully Issued, with nothing between "uploaded" and "published."
8. **Project Information is only what core ERPNext `Project` already carries** — no
   stakeholders, no site data, no healthcare/equipment metadata.

Everything below addresses one of these eight findings.

---

## 1. Project Information — `EGC Project Profile`

**Decision: a 1:1 satellite DocType, not custom fields on `Project`.** A field list this large
(general/parties/site/dates/healthcare) sprinkled onto core `Project` via Custom Field would be
unmaintainable and would collide with `egc_hr`'s existing `custom_egc_*` fields on the same
doctype. A satellite keeps the v1 achievement — **zero custom fields on core `Project`** — intact.

`EGC Project Profile` is named `autoname: "field:project"`, i.e. **its `name` IS the project's
name.** `frappe.get_doc("EGC Project Profile", project)` needs no lookup, and the 1:1 constraint
is enforced by naming itself, not a separate uniqueness check. This is not a second Project
master — it is one row of satellite data per Project, exactly the "EGC Projects extends the
project environment around it" principle from v1 §1.

Do not duplicate a field ERPNext `Project` already owns. Specifically **not** duplicated:
`expected_start_date`/`expected_end_date` (= contractual start/completion),
`actual_start_date`/`actual_end_date`, `status`, `project_type` (reuse core's Select),
`customer` (= Client — see §2).

### Fields

**General**
- `project_code` (Data) — distinct from the Project's own name/number when the two differ.
- `project_stage` (Select: `Design`, `Procurement`, `Construction`, `Commissioning`,
  `Closeout`, `Warranty`) — a construction-lifecycle stage, a different axis from core
  `Project.status` (Open/Completed/Cancelled/On Hold).
- `sector` (Select: `Healthcare`, `Industrial`, `Commercial`, `Infrastructure`, `Other`).
- `delivery_method` (Select: `Design-Bid-Build`, `Design-Build`, `EPC`, `Turnkey`, `Other`).
- `contract_type` (Select: `Lump Sum`, `Unit Price`, `Cost Plus`, `Time & Material`, `Other`).
- `project_description` (Small Text), `work_scope` (Text Editor).
- `contract_value` (Currency) — **explicitly labelled and documented as contract-sourced, not
  an ERPNext actual.** Never conflated with `total_sales_amount` in the Financials tab; shown
  only in Project Information.
- `project_image` (Attach Image).

**Site**
- `country` (Link `Country` — reuse core Frappe doctype), `region`, `city`, `address`
  (Small Text), `latitude`/`longitude` (Float, optional), `time_zone` (Data),
  `site_contact_name`, `site_contact_phone`, `site_contact_email`.

**Dates** — only what core `Project` doesn't already carry:
- `contract_date`, `forecast_completion_date`, `warranty_start_date`, `dlp_end_date`.

**Stakeholders** — child table `stakeholders` (`EGC Project Stakeholder`), see §2.

**Healthcare / Equipment** — child table `equipment_items` (`EGC Project Equipment Item`),
see §3. Deliberately a *child table*, not singular fields, because the v1 brief's own example
(`Radiology Department > MRI-01, MRI-02, CT-01`) already implies multiple pieces of equipment
per project — a fixed set of singular fields would overfit the very first real project.

### Validation
- `validate()` rejects a `project` value that doesn't exist (defensive; the naming already
  guarantees uniqueness).
- Every child row is validated project-consistent where it references another EGC record
  (e.g. an equipment item's `wbs_node` must belong to the same project) via the existing
  `validators.validate_same_project` helper — no new validation pattern invented.

---

## 2. Stakeholders — a reusable model, not hard-coded parties

`EGC Stakeholder Role` — small master (mirrors `EGC Discipline`): `role_name` (unique),
`is_egc_internal` (Check — distinguishes an EGC staff role, which resolves to a `User`, from an
external party role, which does not), `enabled`, `sequence`.

Seeded (idempotent, in `install.py`, `is_egc_internal` marked as noted): `Client`,
`Main Contractor`, `Consultant`, `Architect`, `OEM`, `EGC Project Manager` (internal),
`EGC Site Manager` (internal), `Project Engineer` (internal), `Document Controller` (internal),
`QA/QC` (internal), `HSE` (internal), `Commercial` (internal).

`EGC Project Stakeholder` — child table on `EGC Project Profile`: `role` (Link, reqd),
`party_name` (Data, reqd — the org or person's display name), `organization` (Data, optional),
`user` (Link `User`, optional — set for internal roles so the person can be assigned/notified),
`contact` (Link `Contact`, optional), `email`/`phone` (Data, fetched from `contact`/`user` when
present, else manual), `is_primary` (Check).

**"Siemens / Philips / GE" become data, never schema**: role = `OEM`, `party_name` = whichever
manufacturer applies to that project. No manufacturer is ever a role, a Select option, or a
doctype.

This table is also the **resolution source for the Submittal workflow engine** (§6): a workflow
template step naming `reviewer_role = "Consultant"` resolves, at instantiation time, to that
project's actual `EGC Project Stakeholder` row with `role="Consultant"` and reads its `user`
(or — if the role has no `user` set, e.g. a pure external party with no Frappe login — the step
is recorded against `party_name` for display but cannot be a live in-app reviewer; the UI must
make this distinction obvious rather than silently failing to notify anyone).

`egc_projects/egc_projects/project_profile.py` exposes:
```python
def resolve_role_user(project: str, role_name: str) -> str | None: ...
def get_stakeholders(project: str) -> list[dict]: ...
```

---

## 3. Healthcare / Equipment metadata

`EGC Modality` — small master (ARCH/MECH-style): `modality_name` (MRI, CT, X-Ray, Ultrasound,
Cath Lab, Linear Accelerator, Nuclear Medicine, Other), `enabled`.

`EGC Equipment Manufacturer` — small master: `manufacturer_name` (Siemens Healthineers,
Philips Healthcare, GE HealthCare, Canon Medical, Other), `enabled`. Free-text-extensible (a
user can still type any name via a Data field fallback if truly novel — do not hard-block on
the master list; the field on the child row itself stays a Link so the register stays clean,
but the master is trivially added to, unlike a hard-coded Select).

`EGC Project Equipment Item` — child table on `EGC Project Profile`: `facility` (Data),
`department` (Data), `modality` (Link `EGC Modality`), `wbs_node` (Link `EGC WBS Node`, optional
— ties the equipment to its physical WBS location, e.g. `MRI-01`), `equipment_manufacturer`
(Link `EGC Equipment Manufacturer`), `equipment_model` (Data), `oem_reference` (Data),
`equipment_delivery_target` (Date), `room_ready_target` (Date), `oem_installation_target`
(Date), `commissioning_target` (Date), `notes` (Small Text).

---

## 4. `get_project_context` — extended contract (binding, both backend and frontend build to it)

```python
get_project_context(project) -> {
  project, project_name, status, customer, dates: {expected_start_date, expected_end_date,
    actual_start_date, actual_end_date},
  percent_complete, company, currency,
  permissions: {financials: bool, edit_profile: bool},
  profile: {
    project_code, project_stage, sector, project_image, contract_value,   # or null fields
    key_stakeholders: [{role, role_label, party_name, organization, user, user_full_name}],
      # capped to a header-relevant subset (PM, Site Manager, Client, Consultant, OEM) —
      # the FULL stakeholder/equipment list is fetched separately via get_project_profile()
  } | null   # null ⇒ no EGC Project Profile row exists yet for this project (new-project
             # empty state; the Hub must invite the user to create one, never error)
}
```

New, separate whitelisted methods (added to `api/hub.py` by the Project Information package —
see Wave A ownership below):
```python
get_project_profile(project) -> full profile dict incl. every field + full stakeholders[] +
  equipment_items[]   # gated on Project read permission
save_project_profile(project, data: dict) -> saved profile dict   # gated on `edit_profile`
  permission (EGC Project Manager / EGC Project Engineer / System Manager); loads-or-creates
  the EGC Project Profile doc and applies `data` via doc.update()+doc.save() — reuses native
  Frappe document validation rather than hand-rolling field-by-field writes.
```

---

## 5. Activities — schedule depth and parent rollup

### New fields on `EGC Activity`
- `actual_start_date`, `actual_end_date` (Date).
- `forecast_start_date`, `forecast_end_date` (Date).
- `duration_days` (Int, **read-only, system-computed** — `date_diff(planned_end_date,
  planned_start_date) + 1` when both are set, else **0**. Int is a Frappe numeric fieldtype —
  its DB column is `NOT NULL DEFAULT 0`, and `frappe.db.set_value` (which the rollup engine
  uses) does not run the `cint(None) → 0` coercion a normal `doc.save()` would, so writing a
  bare `None` here throws `IntegrityError`. `0` is unambiguous as "not computed": the formula
  can never itself produce 0 (a same-day span is `date_diff(x, x) + 1 == 1`), so it cannot
  collide with a real duration — the frontend renders 0 as "—", not "0 days". This is the only
  derived-date rule in v2; it does not attempt working-day/calendar logic — that is out of
  scope, matching the brief's explicit "do not implement a fragile home-grown scheduler").
- `is_milestone` (Check).
- `responsible_supplier` (Link `Supplier`, optional) — added alongside the existing
  `responsible_user`. A subcontractor in ERPNext already exists as a `Supplier`; reusing it
  avoids inventing a second party model when §2's Stakeholder model is about project-level
  roles, not activity-level subcontractor assignment.

### Deliberate architecture revision: parent Activities now roll up from children

**v1 said** (§6/§2.6): *"Group activities: percent_complete/status are entered manually in v1
(no roll-up). Roll-up is deferred; do not implement."* The brief explicitly requires this now
("A parent Activity should derive meaningful schedule/progress information from its children").
This is the one place v2 deliberately reverses a v1 decision — recorded here per the v1
document's own escalation rule (§ decision_policy: *"If new requirements require changing
existing architecture, Opus must explicitly reason through the impact and update architecture
documentation/tests accordingly."*).

**New engine module** `egc_projects/egc_projects/activity_control.py`, mirroring
`document_control.py`'s single-writer discipline:

```python
def refresh_activity_rollup(activity: str) -> None: ...   # no-op if is_group != 1
def refresh_ancestors(activity: str) -> None: ...          # walks parent_egc_activity upward,
    # calling refresh_activity_rollup at every level bottom-up so a grandparent picks up an
    # already-recomputed parent's values, not stale ones
```

Rollup rule for a group Activity (computed **only** over its direct children — the bottom-up
walk is what propagates correctness to grandparents):
- `percent_complete` = unweighted average of children's `percent_complete`. (Weighting by
  duration or cost is a real future improvement; averaging is the simplest defensible rule for
  v2 and is stated as a documented limitation, not hidden.)
- `planned_start_date` = `MIN(children.planned_start_date)`;
  `planned_end_date` = `MAX(children.planned_end_date)`.
- `actual_start_date` = `MIN(children.actual_start_date)` **where set**.
  `actual_end_date` = `MAX(children.actual_end_date)` **only when every child has one set** —
  a group cannot have "actually finished" until everything under it has.
- `duration_days` recomputed from the rolled-up planned dates, same rule as a leaf.
- `status`: all children `Completed` ⇒ `Completed`; all children `Not Started` ⇒ `Not Started`;
  otherwise `In Progress` (`Cancelled` children are excluded from this aggregation entirely —
  a cancelled sibling should not force its parent's status).

These fields become **read-only on a group Activity** (`depends_on` in the DocType JSON keys
off `is_group`) — a group's schedule/progress is never hand-edited; only a leaf's is. This must
be called from `on_update`/`on_trash` of `EGC Activity` itself (inserting/editing/deleting *any*
activity calls `refresh_ancestors(self.parent_egc_activity)` after the write).

`is_overdue()` is unaffected — it already reads whatever `planned_end_date`/`status` a row
currently holds, group or leaf.

---

## 6. Activity Dependencies

New DocType `EGC Activity Dependency`: `predecessor` (Link `EGC Activity`, reqd), `successor`
(Link `EGC Activity`, reqd), `dependency_type` (Select: `Finish-to-Start` [default],
`Start-to-Start`, `Finish-to-Finish`, `Start-to-Finish`), `lag_days` (Int, default 0 — negative
permitted for lead), `project` (read-only, `fetch_from: predecessor.project`).

**Validation (server-side, mandatory):**
- `predecessor.project == successor.project` — cross-project dependencies rejected, exactly
  the pattern used everywhere else in this app.
- `predecessor != successor`.
- No duplicate `(predecessor, successor)` pair.
- **No cycles.** A simple BFS from `successor` following existing dependency edges must never
  reach `predecessor` before the new edge is allowed to save. Project-scoped Activity graphs
  are small; no need for anything beyond a plain in-Python graph walk.

**Explicitly out of scope for v2** (per the brief's own boundary — "Critical Path calculation
can remain deferred if implementing it properly would significantly enlarge scope, but the
dependency model must support it later"): dependencies are **recorded, validated, and
displayed** (in the Activity detail workspace's Schedule tab and in the Gantt) — they do **not**
drive automatic forecast-date shifting or a critical-path calculation. That is future work the
schema already supports without alteration.

---

## 7. Submittal Workflows and Ball in Court

This is the largest single piece of the upgrade. It **adds** a multi-step review capability
without breaking the v1 single-response case — 20 existing tests in `test_submittal.py` call
`submittal_control.record_response()` directly and must keep passing unchanged for a submission
that was never given a workflow.

### New DocTypes

**`EGC Submittal Workflow Template`** — reusable, named template: `template_name` (title, reqd),
`description`, `steps` (child table `EGC Submittal Workflow Template Step`).

**`EGC Submittal Workflow Template Step`** (child): `sequence` (Int, reqd — steps sharing the
same `sequence` value run **in parallel**; a submission advances to the next distinct
`sequence` value only once every *required* step at the current one has responded — this is
the sequential-groups/parallel-groups model from the brief expressed with a single integer
column, no separate "group" concept needed), `reviewer_role` (Link `EGC Stakeholder Role`,
reqd), `is_required` (Check, default 1), `label` (Data, optional friendly override for display).

**`EGC Submittal Review Step`** — the **instantiated**, per-submission steps (never edited by a
template change after instantiation — templates are a convenience for creating steps, not a
live binding): `submittal_revision` (Link `EGC Submittal Revision`, reqd), `sequence` (Int),
`reviewer_role` (Link `EGC Stakeholder Role`, optional — kept for display/audit even if a user
could not be resolved), `reviewer_user` (Link `User`, optional — null when the role's
stakeholder has no `user`; see §2), `reviewer_label` (Data, read-only — the display name to show
when there is no `reviewer_user`, e.g. an external party's `party_name`), `is_required` (Check),
`status` (Select: `Pending`, `In Review`, `Responded`, `Skipped` — **engine-owned**), `response`
(Select: the four `REVIEW_RESPONSES` or empty — **engine-owned**), `response_date`,
`responded_by`, `remarks` (all **engine-owned** after creation, same
`assert_engine_authorized()`-style guard as every other engine field in this app).

### The step engine — additions to `submittal_control.py`

```python
def apply_workflow_template(submission: str, template: str) -> None: ...
    # instantiates EGC Submittal Review Step rows from the template, resolving each
    # reviewer_role via project_profile.resolve_role_user() for that submission's project
def add_review_step(submission: str, sequence: int, reviewer_role: str | None,
                     reviewer_user: str | None, is_required: bool = True) -> str: ...
    # ad-hoc single-step addition, for a submission with no template
def start_review(submission: str) -> None: ...
    # called by submit() when review steps exist: marks every step at the lowest pending
    # `sequence` as "In Review", assigns (frappe.desk.form.assign_to) each reviewer_user a
    # ToDo — this is what actually notifies them (see below)
def record_step_response(step: str, response: str, remarks: str | None = None) -> None: ...
    # the caller must BE that step's reviewer_user (or System Manager); records the response,
    # closes that user's ToDo assignment, then evaluates the stage:
    #   - if every required step at this sequence is now Responded:
    #       - any response was Revise & Resubmit or Rejected ⇒ the WHOLE submission is
    #         immediately Responded with that response (a single rejecting/returning reviewer
    #         stops the cycle — standard construction submittal semantics); remaining Pending
    #         steps at later sequences are marked Skipped.
    #       - otherwise ⇒ advance: the next-lowest `sequence` with Pending steps becomes
    #         In Review (repeat start_review's assignment logic for that stage); if there is no
    #         further sequence, the submission is Responded with Approved (if every response
    #         was Approved) or Approved with Comments (if any response carried comments but
    #         none rejected/returned it) — a small, fully deterministic aggregation table, not
    #         a generic rules engine.
def get_ball_in_court(submission: str) -> dict: ...
    # {users: [...], labels: [...], is_external_only: bool} — derived live from the current
    # In Review step rows; never stored as an independently-editable field
```

**Backward compatibility (mandatory):** a submission with **zero** `EGC Submittal Review Step`
rows behaves exactly as v1 — `submit()` leaves it `Submitted` (not auto-advanced into a review
stage), and the existing top-level `record_response(submission, response, remarks,
response_date)` continues to work exactly as today, unchanged. Workflow steps are additive:
`record_response()` must remain callable directly for the simple case; the step machinery is
only exercised when steps actually exist on that submission.

### Ball in Court — the derived label

`EGC Submittal Revision` gains `ball_in_court_label` (Data, **read-only, engine-set** — e.g.
`"Consultant — Ahmed Hassan"`, or `"Consultant, Siemens (OEM)"` when a parallel stage has
multiple current reviewers). `EGC Submittal` gains the same field (mirroring the existing
`current_submission_label` pattern), recomputed by `refresh_submittal_state()` whenever the
current submission's review-step state changes. **Never independently editable** — this is the
same "one writer per derived value" rule as document approval status.

### Notifications — reuse Frappe's own mechanisms, per the brief's explicit instruction

- **Ball-in-court delivery IS `frappe.desk.form.assign_to`.** Assigning a ToDo to the current
  stage's `reviewer_user`(s) when a stage opens, and closing it when they respond, gives
  "assigned for review" and "response required" for free — Frappe's core assignment flow
  already creates a `Notification Log` entry and surfaces the item in that user's assignment
  list and notification bell. No parallel notification store is built for this.
- The remaining bullets from the brief (submission received, response recorded, revise &
  resubmit, new revision submitted, upcoming due date, overdue) are covered by a small
  `egc_projects/egc_projects/notifications.py` using the documented core helper
  `frappe.desk.doctype.notification_log.notification_log.enqueue_create_notification(...)`.
  Due-date/overdue reminders run once daily via `scheduler_events` (mirroring `egc_hr`'s own
  `alert_expiring_documents` pattern) and must not re-notify the same user for the same step
  twice — dedupe by checking for an existing unread `Notification Log` referencing that step
  before creating another.
- `EGC Submittal Workflow Template` is where "Standard Consultant Review" /
  "Siemens Material Approval" style reuse lives — apply a template rather than rebuilding a
  reviewer sequence by hand, exactly per the brief.

### 7a. Expanded Submittal metadata

Per the brief's "Expand Submittal Information": fields that manage a real construction
submission, not a bare identity. Added where they don't already exist and don't duplicate
something derivable — `related Activities` is not a field, it is the existing
`EGC Activity Link` relationship (§ v1 doc), and is not repeated here.

New on **`EGC Submittal`**: `responsible_party` (Data — the contractor/vendor responsible for
the submission; free text, matching the same "don't force a bad Customer/Supplier shoehorn"
call made for stakeholders in §2), `received_from` (Data), `submittal_manager` (Link `User`),
`ball_in_court` (Data, **read-only, engine-set** — mirrors `current_submission_label`'s pattern,
see §7's Ball in Court subsection), `specification_section` (Data, optional, reserved for future
spec-section cross-referencing — not used by any logic in v2).

New on **`EGC Submittal Revision`**: `required_submission_date`, `required_approval_date`,
`final_due_date`, `required_on_site_date` (all Date), `lead_time_days` (Int, optional,
informational only — no scheduling logic reads it), `ball_in_court_label` (Data, **read-only,
engine-set**, per §7's Ball in Court subsection).

`current_due_date` on `EGC Submittal` (already existed, fetched from the current submission's
`due_date`) continues to mean "when a response is due" — `final_due_date` is a distinct,
contract-level date and is never conflated with it.

---

## 8. My Open Items — an extensible action-item registry

Per the brief: *"do not hard-code the Overview separately for every future module... the
architecture should eventually be able to aggregate [Submittal Review, RFI Response, MIR
Review, ...]. Current implementation only needs to support current modules."*

`egc_projects/egc_projects/action_items.py` — a plain registry, the same shape as
`relationships.ALLOWED_LINK_DOCTYPES`, not a generic DocType-based framework (that would be
overbuilding for two sources):

```python
def get_open_items_for_user(user: str, project: str | None = None) -> list[dict]:
    # returns a normalised shape regardless of source:
    # {source, title, doctype, name, project, due_date, is_overdue, url}
    # v2 sources, hard-wired here (adding RFI/MIR/etc. later is new entries in this function,
    # not a schema change):
    #   - EGC Submittal Review Step where reviewer_user = user and status = "In Review"
    #   - EGC Activity where responsible_user = user and is_overdue()
```

---

## 9. Drawings — Sets, Areas, and a controlled publish state

**`EGC Drawing Set`** — project-scoped (like `EGC WBS Node`): `project`, `set_code`, `set_name`,
`sequence`, `issue_date`, `description`. `autoname: format:{project}-{set_code}`. Configurable
per project — "Tender", "IFC", "Addendum 01" are conventions, not a fixed enum.

**`EGC Drawing Area`** — project-scoped, same shape: `project`, `area_code`, `area_name`,
`sequence`, `wbs_node` (optional Link, ties the area to a physical WBS location),
`description`. `autoname: format:{project}-{area_code}`. Deliberately **not** a general
Location hierarchy — this is a flat, drawing-management-only grouping, per the brief's explicit
boundary ("Do not confuse Drawing Area with the future full Project Location hierarchy").

New fields on **`EGC Project Document`** (not a new doctype — Sets/Areas apply to any
controlled document, but are only shown/used in the UI when `document_type.is_drawing = 1`,
consistent with v1's "a Drawing is a Document with Drawing-specific semantics" rule):
`drawing_set` (Link `EGC Drawing Set`, optional, same-project validated), `drawing_area` (Link
`EGC Drawing Area`, optional, same-project validated), `drawing_date` (Date), `received_date`
(Date).

### Publish/current workflow — additive, does not touch existing revision semantics

New field on **`EGC Project Document Revision`**: `readiness` (Select: `Uploaded` [default],
`Reviewed`, `Ready to Publish` — editable only pre-submit, i.e. while `docstatus = 0`). This
gives document controllers an internal draft-review state before they commit to issuing —
**`submit()` remains the single act of publishing/issuing**, exactly as v1's `document_control.py`
already implements it. `readiness` is purely informational metadata on the draft; it introduces
no new lifecycle state, no new engine function, and does not change `revision_status`'s four
values (`Draft`/`Issued`/`Superseded`/`Cancelled`) at all. Existing tests are unaffected because
the field defaults sanely and nothing reads it except the new UI.

---

## 10. Financials — drill-down

New read-only, permission-gated endpoints in `api/hub.py` (owned, in this upgrade, by whichever
package implements the Financials tab — see Wave E):

```python
get_financial_transactions(project, metric) -> list[dict]
    # metric ∈ {"billed", "purchase_cost", "expense_claims", "consumed_material_cost",
    #           "timesheet_cost", "sales_order_value"}
    # returns the underlying ERPNext rows (Sales Invoice / Purchase Invoice / Expense Claim /
    # Stock Entry / Timesheet, filtered by project and docstatus=1) that sum to the
    # corresponding get_financials() figure. Read-only. Gated exactly like get_financials()
    # (constants.FINANCIAL_ROLES). Never recomputes the total — it is a read of the same
    # transactions ERPNext already used to arrive at the Project's own aggregate field, so the
    # drill-down and the headline figure can never disagree.
```

---

## 11. Project health (Overview redesign)

Per the brief's explicit caution — *"Only derive health where the rules are defensible"** — v2
implements exactly these, and no more:
- **Schedule health**: `red` if any Activity is overdue and none has been touched (status
  changed) in the last 14 days; `orange` if any Activity is overdue; else `green`.
- **Submittals health**: `red` if any Submittal is overdue; `orange` if any is `Revise &
  Resubmit`/`Rejected` and not yet resubmitted; else `green`.
- **Documents/Drawings health**: `orange` if any drawing's current revision is
  `Under Review`/`Revise & Resubmit` past its submittal's due date; else `green`.
- **Financials health**: `red` if `gross_margin < 0`; else `green`. (Deliberately the simplest
  possible rule — a fabricated "budget variance" indicator with no budget data behind it would
  violate the brief's own instruction not to fake a metric.)

---

## 12. File ownership map (for delegation — avoids concurrent-edit conflicts)

| Area | Owns |
|---|---|
| `api/hub.py` | Project Information package (Wave A) extends `get_project_context`; Financials package (Wave E) adds drill-down. No other package edits this file this upgrade — new endpoint groups get their own module. |
| `api/documents.py` (new) | Documents Tool package (Wave A) |
| `api/activities.py` (new) | Activities/Schedule package (Wave B) |
| `api/submittals.py` (new) | Submittal Workflow package (Wave C) |
| `api/drawings.py` (new) | Drawings package (Wave D) |
| `egc_projects/project_profile.py` (new) | Project Information package |
| `egc_projects/activity_control.py` (new) | Activities/Schedule package |
| `egc_projects/submittal_control.py` | Submittal Workflow package (additive only — existing functions/signatures untouched) |
| `egc_projects/document_control.py` | Drawings package may **add** a `readiness` pass-through; must not change existing revision-state functions |
| `egc_projects/action_items.py` (new) | Overview/Actions package (Wave E) |
| `egc_projects/notifications.py` (new) | Submittal Workflow package |
| every new DocType directory | the package that introduces it, listed per-package at delegation time |

**Frontend wrapper convention (settled during Wave A, applies to every later wave):** each new
`api/<domain>.py` module gets its own thin frontend wrapper file next to the Vue components that
use it (e.g. `components/documents_api.js` for `api/documents.py`), following `api.js`'s exact
`frappe.call`/error-extraction pattern, rather than every package appending to the shared
`api.js`. This is deliberate, not a shortcut left for later cleanup: `api.js` would otherwise
become exactly the same concurrent-edit bottleneck the backend split was designed to avoid, just
moved to the frontend. `api.js` itself keeps only what already existed before this upgrade,
plus Project Information's two methods (that package's backend lived in `hub.py`, so its
wrapper does too, consistently).

Splitting `api/hub.py`'s growth into per-domain modules (`api/documents.py`,
`api/activities.py`, `api/submittals.py`, `api/drawings.py`) is itself a deliberate, disclosed
decision: v1's single `hub.py` was already large before this upgrade, and letting every wave
append to one file would make safe parallel delegation impossible. Each new module follows
`hub.py`'s existing conventions verbatim (`require_project_permission` first, filter allow-lists,
no raw SQL).

---

## 13. What remains deferred (unchanged from v1, plus this upgrade's own boundaries)

Still out of scope: BOQ, Budget, Forecast, Commitment, Change Management, RFI, MIR, WIR, FIR,
ITP, NCR, Punch List, Daily Log, HSE module, procurement packages, material tracking, resource
planning, BIM, commissioning module, full Location hierarchy, CPM/critical-path calculation,
P6/MSP import, offline mobile, drawing markup/pins/overlays, AI extraction.

New-this-upgrade boundaries, stated explicitly so a delegated agent doesn't overbuild:
automatic date-shifting from Activity Dependencies (recorded/validated only), a generic
workflow-template engine beyond the sequence-based step model in §7, a second notification
store beyond Frappe's own assignment/`Notification Log`, weighted (vs. simple-average) progress
roll-up, and a full Project Location hierarchy (Drawing Area is a flat, drawing-only grouping).
