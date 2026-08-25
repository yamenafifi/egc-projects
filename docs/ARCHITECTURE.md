# EGC Projects — Authoritative Architecture (v1)

This document is **binding**. Implementation agents may make local implementation choices
inside these boundaries; they may not redefine sources of truth, DocType relationships,
revision semantics, project authorization, or application boundaries. If an instruction here
appears impossible, report it — do not silently redesign.

Target: **Frappe v16.31 / ERPNext v16.32**, Python 3.14, site `dev.localhost`.

---

## 0. Prime directives

1. **ERPNext `Project` is the canonical project record.** `egc_projects` never creates a
   competing project master. Every EGC record belongs to exactly one `Project`.
2. **No core modification.** `apps/frappe`, `apps/erpnext`, `apps/hrms` are read-only.
   Extend via our own DocTypes and `hooks.py` only.
3. **No second accounting ledger.** Financial figures are *read* from ERPNext.
4. **One authoritative source per displayed value.** Anything denormalized is written by the
   system (`db_set` / controller), never editable by a user.
5. **Server-side validation is mandatory** for every project-isolation rule. Client-side
   `get_query` filters are UX, not enforcement.

---

## 1. Module & repository layout

```
egc_projects/
  hooks.py                        # OPUS-OWNED. Agents must not edit.
  install.py                      # OPUS-OWNED (roles, masters bootstrap)
  modules.txt, patches.txt        # OPUS-OWNED
  egc_projects/                   # module dir
    doctype/<snake_case>/         # one dir per DocType
    page/egc_project_hub/         # Vue-based Desk Page
    report/<snake_case>/          # query/script reports
    document_control.py           # revision lifecycle engine (single source of truth)
    submittal_control.py          # submittal lifecycle engine
    relationships.py              # activity-link helpers + allowed target registry
    validators.py                 # shared project-isolation validators
    constants.py                  # status enums / magic values, single definition
  api/
    hub.py                        # whitelisted Project Hub endpoints
  public/
    js/                           # bundles + doctype client scripts
  tests/
    test_*.py
  docs/
```

**Concurrency rule:** each work package owns a disjoint file list. `hooks.py`,
`modules.txt`, `patches.txt`, `install.py`, `constants.py` are owned by the lead (Opus).
An agent that needs a hook entry or a constant *reports* it; it does not edit those files.

---

## 2. DocType catalogue

All DocTypes are in module **EGC Projects**, `custom: 0`, committed as JSON (developer mode).

### 2.1 Masters (global, not project-scoped)

| DocType | Naming | Key fields |
|---|---|---|
| `EGC Discipline` | `field:discipline_code` | `discipline_code` (Data, unique, reqd, uppercase), `discipline_name` (Data, reqd, title field), `enabled` (Check, dflt 1), `description` |
| `EGC Document Type` | `field:document_type_name` | `document_type_name` (Data, reqd), `abbreviation` (Data), `is_drawing` (Check), `enabled` (Check, dflt 1), `description` |
| `EGC Submittal Type` | `field:submittal_type_name` | `submittal_type_name` (Data, reqd), `abbreviation`, `enabled` (Check, dflt 1), `description` |

Seeded on install (idempotent) by `install.py`:
- Disciplines: ARCH/Architectural, MECH/Mechanical, ELEC/Electrical, CIVIL/Civil.
- Document Types: `Drawing` (is_drawing=1), `Specification`, `Method Statement`,
  `Technical Data`, `Calculation`, `Certificate`, `Report`, `Other`.
- Submittal Types: `Shop Drawing`, `Material Submittal`, `Method Statement`, `Calculation`,
  `Technical Data`, `Product Data`, `Sample`, `Mockup`, `Certificate`.

### 2.2 `EGC WBS Node` — project breakdown structure

Tree DocType (`is_tree: 1`, `NestedSet`, `nsm_parent_field: parent_egc_wbs_node`).

| Field | Type | Notes |
|---|---|---|
| `project` | Link `Project` | reqd, `in_standard_filter` |
| `wbs_code` | Data | reqd, **user-supplied**, unique **per project** |
| `wbs_name` | Data | reqd, `title_field` |
| `parent_egc_wbs_node` | Link `EGC WBS Node` | tree parent; `ignore_user_permissions: 0` |
| `is_group` | Check | |
| `sequence` | Int | sibling ordering; default 0 |
| `discipline` | Link `EGC Discipline` | optional classification only |
| `status` | Select | `Active`\|`On Hold`\|`Completed`\|`Cancelled`, dflt `Active` |
| `description` | Small Text | |
| `lft`,`rgt`,`old_parent` | Int/Int/Data | hidden, framework-managed |

- **Naming:** `naming_rule: Expression`, `autoname: format:{project}-{wbs_code}`.
- `show_title_field_in_link: 1`, `search_fields: wbs_code,wbs_name,project`.
- **Validation (server):** parent must exist, be `is_group=1`, and have the **same `project`**.
  Changing `project` is blocked when children exist. `wbs_code` unique per project.
  Arbitrary depth allowed. Multiple roots (one per project) allowed — do **not** call
  `validate_one_root()`.
- Tree view: `egc_wbs_node_tree.js` with a mandatory `Project` filter, using a whitelisted
  `get_children` that enforces the project filter server-side.
- **Reserved for later (do not build):** budget, BOQ, cost codes, work packages.

### 2.3 `EGC Activity` — execution breakdown

Tree DocType (`is_tree: 1`, `NestedSet`, `nsm_parent_field: parent_egc_activity`).
The **same DocType recursively** — no Sub-Activity DocType.

| Field | Type | Notes |
|---|---|---|
| `project` | Link `Project` | reqd, `in_standard_filter` |
| `activity_code` | Data | reqd, user-supplied, unique **per project** |
| `activity_name` | Data | reqd, `title_field` |
| `parent_egc_activity` | Link `EGC Activity` | same project only |
| `is_group` | Check | |
| `sequence` | Int | |
| `wbs_node` | Link `EGC WBS Node` | same project only |
| `discipline` | Link `EGC Discipline` | |
| `planned_start_date` / `planned_end_date` | Date | finish >= start |
| `status` | Select | `Not Started`\|`In Progress`\|`On Hold`\|`Completed`\|`Cancelled`, dflt `Not Started` |
| `percent_complete` | Percent | 0–100; `Completed` ⇒ 100; `Not Started` ⇒ 0 |
| `responsible_user` | Link `User` | |
| `description` | Text Editor | scope / notes |
| `lft`,`rgt`,`old_parent` | | framework-managed |

- **Naming:** `format:{project}-{activity_code}`.
- Overdue is **derived, never stored**: `planned_end_date < today AND status NOT IN
  ('Completed','Cancelled')`.
- Group activities: `percent_complete`/`status` are entered manually in v1 (no roll-up).
  Roll-up is deferred; do not implement.
- **Reserved for later (do not build):** dependencies/FS-SS-FF-SF, lag, baselines, actual
  dates, calendars, critical path, quantities, cost loading, readiness engine.

### 2.4 Controlled documents

#### `EGC Project Document` — document *identity*

| Field | Type | Notes |
|---|---|---|
| `project` | Link `Project` | reqd |
| `document_number` | Data | reqd, **user-supplied** (external doc-control conventions), unique per project |
| `title` | Data | reqd, `title_field` |
| `document_type` | Link `EGC Document Type` | reqd |
| `discipline` | Link `EGC Discipline` | |
| `originator` | Data | |
| `wbs_node` | Link `EGC WBS Node` | optional, same project |
| `description` | Small Text | |
| `current_revision` | Link `EGC Project Document Revision` | **read_only, system-set** |
| `current_revision_label` | Data | **read_only, system-set** (denormalized for registers) |
| `current_revision_date` | Date | **read_only, system-set** |
| `current_file` | Attach | **read_only, system-set** (mirrors current revision's file) |
| `document_status` | Select | **read_only, system-set**: `No Revision`\|`Draft`\|`Issued`\|`Cancelled` |
| `approval_status` | Select | **read_only, system-set**: `Not Submitted`\|`Under Review`\|`Approved`\|`Approved with Comments`\|`Revise & Resubmit`\|`Rejected` |

- **Naming:** `format:{project}-{document_number}`.
- A Drawing is `document_type` whose master has `is_drawing = 1`. **There is no separate
  Drawing DocType.**

#### `EGC Project Document Revision` — document *revision*

`is_submittable: 1`. **docstatus is the revision-integrity mechanism.**

| Field | Type | Notes |
|---|---|---|
| `document` | Link `EGC Project Document` | reqd |
| `project` | Link `Project` | `fetch_from: document.project`, read_only, `fetch_if_empty: 0` |
| `revision` | Data | reqd, e.g. `00`,`01`,`A`; unique per document |
| `revision_seq` | Int | **system-set** on insert = max(existing)+1; the ordering authority |
| `file` | Attach | reqd; **not** `allow_on_submit` |
| `revision_date` | Date | reqd, dflt today |
| `issue_date` | Date | |
| `revision_status` | Select | `Draft`\|`Issued`\|`Superseded`\|`Cancelled`; **read_only + allow_on_submit**, system-written only |
| `superseded_by` | Link self | read_only + allow_on_submit, system-written |
| `reason_for_revision` | Data | |
| `remarks` | Small Text | |

- **Naming:** `format:{document}-R{revision}`.
- **Lifecycle (the ONLY implementation lives in `document_control.py`):**
  - `docstatus 0` ⇒ `revision_status = Draft`. Editable, file replaceable.
  - `submit()` ⇒ `Issued`. Frappe natively blocks edits to non-`allow_on_submit` fields,
    so **the file of an issued revision can never be replaced** — this is the revision
    integrity guarantee, enforced by the framework, not by our code.
  - On submit, any previously-current issued revision becomes `Superseded` with
    `superseded_by` set; the new one becomes the document's current revision.
  - `cancel()` ⇒ `Cancelled`; the document's current revision is recomputed.
  - **Current revision =** highest `revision_seq` among rows with `docstatus = 1` and
    `revision_status IN ('Issued')`. Recomputed by `document_control.refresh_document_state()`
    which is the sole writer of every `current_*`, `document_status`, `approval_status` field.
  - `on_update_after_submit` must reject any change to `revision_status`/`superseded_by` that
    did not come from the lifecycle engine (guard flag), so an API caller cannot rewrite history.
- **Deletion:** only `Draft` (docstatus 0) revisions may be deleted. Cancelled/Issued rows stay.

#### `approval_status` derivation — the anti-conflict rule (prompt §13)

`EGC Project Document.approval_status` describes **only the current revision**. It is derived
by `refresh_document_state()` as:

1. Find the current revision (as above). If none ⇒ `Not Submitted`.
2. Find all `EGC Submittal Revision` rows (docstatus = 1, not `Cancelled`) that contain **that
   exact document revision** in their `documents` child table, ordered by `submission_seq` desc.
3. If none ⇒ `Not Submitted`.
4. Else take the latest such submittal revision:
   - `submission_status` in (`Submitted`,`Under Review`) ⇒ `Under Review`
   - `submission_status = Responded` ⇒ map its `response` directly
     (`Approved`, `Approved with Comments`, `Revise & Resubmit`, `Rejected`).

Consequence, as required: **Rev 03 never inherits Rev 02's approval.** The register shows
`current_revision_label` + `approval_status`, both derived from the same single computation.

### 2.5 Submittals

#### `EGC Submittal` — submittal *identity*

| Field | Type | Notes |
|---|---|---|
| `project` | Link `Project` | reqd |
| `submittal_number` | Data | reqd, user-supplied, unique per project |
| `title` | Data | reqd, `title_field` |
| `submittal_type` | Link `EGC Submittal Type` | reqd |
| `discipline` | Link `EGC Discipline` | |
| `wbs_node` | Link `EGC WBS Node` | optional, same project |
| `description` | Small Text | |
| `current_submission` | Link `EGC Submittal Revision` | read_only, system-set |
| `current_submission_label` | Data | read_only, system-set |
| `submittal_status` | Select | read_only, system-set: `Draft`\|`Submitted`\|`Under Review`\|`Approved`\|`Approved with Comments`\|`Revise & Resubmit`\|`Rejected` |
| `current_due_date` | Date | read_only, system-set |
| `last_response_date` | Date | read_only, system-set |

- **Naming:** `format:{project}-{submittal_number}`.

#### `EGC Submittal Revision` — one submission/review cycle

`is_submittable: 1`.

| Field | Type | Notes |
|---|---|---|
| `submittal` | Link `EGC Submittal` | reqd |
| `project` | Link `Project` | fetch_from `submittal.project`, read_only |
| `revision_label` | Data | reqd, e.g. `00`; unique per submittal |
| `submission_seq` | Int | system-set = max+1; ordering authority |
| `date_submitted` | Date | |
| `due_date` | Date | review due date |
| `submitted_by` | Link `User` | |
| `reviewer` | Link `User` | |
| `submission_status` | Select | `Draft`\|`Submitted`\|`Under Review`\|`Responded`\|`Cancelled`; read_only + allow_on_submit, engine-written |
| `response` | Select | ``\|`Approved`\|`Approved with Comments`\|`Revise & Resubmit`\|`Rejected`; read_only + allow_on_submit, engine-written |
| `response_date` | Date | read_only + allow_on_submit |
| `responded_by` | Link `User` | read_only + allow_on_submit |
| `response_remarks` | Text | read_only + allow_on_submit |
| `documents` | Table `EGC Submittal Document Item` | the controlled revisions being submitted |

- **Naming:** `format:{submittal}-S{revision_label}`.
- **Lifecycle — explicit domain code, NOT a Frappe Workflow.** Rationale: the lifecycle is
  coupled to `docstatus` and to derived state on two parent DocTypes; a Frappe Workflow would
  become a second, divergent source of truth for the same transitions. Recorded decision.
  Transitions (all in `submittal_control.py`, all whitelisted with permission checks):
  - insert (docstatus 0) ⇒ `Draft`
  - `submit()` ⇒ `Submitted` (requires ≥1 document row, each an **Issued** revision)
  - `mark_under_review()` ⇒ `Under Review` (from `Submitted`)
  - `record_response(response, remarks, date)` ⇒ `Responded` + stores response
    (from `Submitted`/`Under Review`; **irreversible** — a response is history)
  - `create_next_revision()` ⇒ new Draft `EGC Submittal Revision` with `revision_label` =
    next sequential label, `submission_seq` = max+1, copying nothing from the response.
    Allowed only when the latest submission is `Responded`. Previous rows are never touched.
  - `cancel()` ⇒ `Cancelled`.
- `EGC Submittal.submittal_status` = derived from the **latest non-cancelled** submission
  (`Responded` ⇒ its `response`; else its `submission_status`). Written only by
  `submittal_control.refresh_submittal_state()`.
- After any submittal-revision state change, call
  `document_control.refresh_document_state()` for every distinct document referenced by its
  `documents` table, so `approval_status` on documents stays correct.

#### `EGC Submittal Document Item` (child)

| Field | Type | Notes |
|---|---|---|
| `document_revision` | Link `EGC Project Document Revision` | reqd, `in_list_view` |
| `document` | Link `EGC Project Document` | fetch_from, read_only |
| `revision` | Data | fetch_from `document_revision.revision`, read_only |
| `document_title` | Data | fetch_from `document_revision.document.title` (or set in controller), read_only |

Validation: every `document_revision` must belong to the **same project** as the parent
submittal, must be `docstatus = 1`, and must not repeat within the table.

### 2.6 `EGC Activity Link` — the many-to-many relationship layer

Standalone DocType (not a child table) so both directions query cheaply and permissions apply.

| Field | Type | Notes |
|---|---|---|
| `activity` | Link `EGC Activity` | reqd |
| `project` | Link `Project` | read_only, **system-set from `activity.project`** |
| `link_doctype` | Link `DocType` | reqd; `options` restricted by `get_query` **and** validated server-side against `relationships.ALLOWED_LINK_DOCTYPES` |
| `link_name` | Dynamic Link (`options: link_doctype`) | reqd |
| `link_title` | Data | read_only, system-set (display) |
| `link_purpose` | Select | `Reference`\|`Requirement`, dflt `Reference` |
| `is_blocking` | Check | dflt 0 — reserved for the future readiness engine |
| `required_status` | Data | reserved, nullable, unused in v1 |
| `stage` | Data | reserved, nullable, unused in v1 |
| `remarks` | Small Text | |

- **Naming:** `hash`. Unique index enforced in `validate` on
  (`activity`,`link_doctype`,`link_name`).
- `ALLOWED_LINK_DOCTYPES` (v1) = `{"EGC Project Document", "EGC Submittal"}`. It is a plain
  registry constant; adding `EGC RFI`, `EGC MIR`, ... later is a one-line change and needs no
  schema change. **Do not** add numbered hard-coded relationship fields anywhere.
- **Validation:** target record's `project` must equal `activity.project`.
- UI: a shared client helper renders "Linked Documents & Submittals" on the Activity form and
  "Related Activities" on Document/Submittal forms, both with add/remove.

---

## 3. Naming & uniqueness summary

| Record | Identifier | Source | Uniqueness |
|---|---|---|---|
| WBS Node | `wbs_code` | user | per project |
| Activity | `activity_code` | user | per project |
| Document | `document_number` | user (often external) | per project |
| Document Revision | `revision` | user | per document |
| Submittal | `submittal_number` | user | per project |
| Submittal Revision | `revision_label` | system-suggested, user-editable while Draft | per submittal |

Document names are globally unique via the `{project}-{code}` expression, so two projects may
legitimately hold the same `document_number`. All uniqueness checks are **server-side** in
`validate`, case-insensitively normalised (`strip()`), in addition to any DB index.

---

## 4. Permissions

Roles created by `install.py` (idempotent, exported as fixtures):

| Role | Intent |
|---|---|
| `EGC Project Manager` | full control of all EGC project data + financial visibility |
| `EGC Project Engineer` | create/edit WBS, Activities, links; read documents/submittals |
| `EGC Document Controller` | full control of Documents, Revisions, Submittals |
| `EGC Project Viewer` | read-only, no financials |

- Every EGC DocType carries a `project` Link field, so **standard Frappe User Permissions on
  `Project` cascade automatically** — no custom `permission_query_conditions` needed for
  project isolation of our own DocTypes. This is deliberate and must not be replaced with a
  hand-rolled filter.
- **Every** whitelisted method in `api/hub.py` must begin with
  `frappe.has_permission("Project", "read", doc=project, throw=True)`.
- **Financials** are additionally gated: the caller must have `read` permission on `Project`
  *and* hold one of `EGC Project Manager`, `Projects Manager`, `Accounts User`, `Accounts
  Manager`, or `System Manager`. `EGC Project Viewer`/`Engineer` alone get no financial data;
  the API raises `frappe.PermissionError`, it does not return zeros.
- Attachments inherit Frappe's private-file behaviour. `Attach` fields must **not** be
  configured to force public files.

---

## 5. Project Hub

- **Entry points:** (a) Workspace `EGC Projects` (app landing), (b) a
  `Open in EGC Projects` button added to the ERPNext `Project` form via `doctype_js`
  (no custom fields are added to `Project` — keeps upgrade surface at zero).
- **Implementation:** a Frappe **Desk Page** `egc-project-hub`, rendered by a Vue 3 SFC
  bundle (`egc_project_hub.bundle.js`) — Vue 3 ships with Frappe v16 and its esbuild pipeline
  compiles SFCs natively (`esbuild-plugin-vue3`).
- **Route carries context:** `/app/egc-project-hub/<project>/<tab>`; last project is also kept
  in `localStorage` so re-entry restores context. Switching tabs never loses the project.
- **Tabs:** Overview, WBS, Activities, Submittals, Drawings, Financials.
- The Hub is a **presentation/orchestration layer only**. All data comes from whitelisted API
  methods over ordinary DocTypes; every record remains reachable through its native
  list/form/report. No business state lives only in the frontend.
- Every register row deep-links to the underlying Frappe form.

### `api/hub.py` contract (stable — later work packages depend on it)

```
get_project_context(project)      -> {project, project_name, status, customer, dates, %complete,
                                      company, currency, permissions:{financials: bool}}
get_overview(project)             -> {activities:{total,completed,in_progress,not_started,overdue},
                                      submittals:{total,approved,approved_with_comments,
                                                  under_review,revise_resubmit,rejected,overdue},
                                      drawings:{total,issued,pending_review},
                                      recent:{document_revisions[], submittal_responses[],
                                              activity_updates[]}}
get_wbs_tree(project)             -> [{name,wbs_code,wbs_name,parent,is_group,sequence,status,discipline}]
get_activities(project, filters)  -> [{...activity fields, is_overdue, link_counts}]
get_submittals(project, filters)  -> [{...}]
get_drawings(project, filters)    -> [{document, number, title, discipline, current_revision_label,
                                       approval_status, current_revision_date, current_file}]
get_document_revisions(document)  -> [{revision, revision_seq, revision_status, file,
                                       revision_date, issue_date, remarks, docstatus}]
get_financials(project)           -> {billed, purchase_cost, expense_claims, consumed_material_cost,
                                      timesheet_cost, billable, sales_order_value, estimated_costing,
                                      gross_margin, per_gross_margin, currency}
```

Filters are validated against an allow-list of fieldnames; never interpolate caller input
into SQL. Use `frappe.qb` / `frappe.get_all`.

---

## 6. Financials — read-only from ERPNext

ERPNext maintains these as persisted fields on `tabProject`, written by ERPNext/HRMS
controllers (`Project.update_costing()`, `calculate_total_purchase_cost()`,
`Stock Entry.update_project()`, HRMS `employee_project.py`):

| Hub label | ERPNext field | Written by |
|---|---|---|
| Billed | `total_billed_amount` | `Project.update_billed_amount()` (Sales Invoice) |
| Purchase Cost | `total_purchase_cost` | `calculate_total_purchase_cost()` (Purchase Invoice) |
| Expense Claims | `total_expense_claim` | HRMS custom field, `hrms/overrides/employee_project.py` |
| Consumed Material Cost | `total_consumed_material_cost` | `Stock Entry` |
| Timesheet Cost | `total_costing_amount` | `Project.update_costing()` (Timesheet Detail) |
| Billable | `total_billable_amount` | same |
| Sales Order Value | `total_sales_amount` | `Project.update_sales_amount()` |
| Gross Margin / % | `gross_margin`, `per_gross_margin` | `Project.calculate_gross_margin()` |

`get_financials()` **reads these fields directly** with `frappe.db.get_value`. It must not
re-aggregate invoices itself — that would create a second, divergent source of truth.
`total_expense_claim` is read defensively (`meta.has_field`) because it is an HRMS custom
field, not core ERPNext.

---

## 7. Reports (native, query/script)

- `EGC Drawing Register` — Script Report. Filters: Project (reqd), Discipline, Approval Status,
  Document Type. Columns: Drawing No, Title, Discipline, Current Rev, Approval Status,
  Revision Date, Document link. Only `document_type.is_drawing = 1`.
- `EGC Submittal Log` — Script Report. Filters: Project (reqd), Submittal Type, Discipline,
  Status, Overdue only. Columns: Submittal No, Title, Type, Discipline, Current Submission,
  Status, Due Date, Days Overdue, Last Response.
- `EGC Activity Status Summary` — Script Report. Filters: Project (reqd), WBS Node, Discipline,
  Status. Columns: Activity Code, Name, WBS, Discipline, Planned Start/Finish, Status,
  % Complete, Overdue, Responsible. Indented by tree depth.

All reports must respect permissions (`frappe.has_permission("Project","read",...)`).

---

## 8. Testing

`egc_projects/tests/` — one module per domain. Tests run with
`bench --site dev.localhost run-tests --app egc_projects`. Tests must create their own
fixtures (a dedicated test Project) and clean up; they must never depend on live site data.
Mandatory coverage matches the 10 acceptance scenarios in the build brief.

---

## 9. Explicitly deferred (do not implement)

BOQ, budgets, commitments, forecasting, change events/orders, RFI/MIR/WIR/FIR/ITP/NCR,
punch lists, daily logs, HSE, procurement, material tracking, resource planning, BIM,
commissioning, warranty, locations, CPM/scheduling engines, P6/MSP import, offline mobile,
drawing markup/pins, AI extraction, roll-up of activity progress, readiness engine.
