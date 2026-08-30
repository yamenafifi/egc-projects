# CLAUDE.md

Guidance for Claude Code (or any future contributor) working in this repository.

## What this is

`egc_projects` is a custom Frappe **v16** app that upgrades ERPNext project management for EGC,
a specialty healthcare contractor. It adds construction-management semantics that ERPNext does
not have — a real WBS, an execution Activity hierarchy, controlled documents with revision
history, a Drawing Register, and Submittals with review cycles — **around** the existing
ERPNext `Project`, which stays the canonical project record.

**Read `docs/ARCHITECTURE.md` before writing any code.** It is the binding design document:
which DocType owns which fact, how revisions stay immutable, and which values are derived
rather than stored. Everything in this app follows from it.

## This repo *is* the bench app directory

Unlike `egc_hr`, there is no repo/bench split and no rsync step. The git repository lives at
`frappe_docker/development/frappe-bench/apps/egc_projects` inside the dev bench, which is the
directory the container mounts and runs. Edit here, migrate here, test here, commit here.
The dev bench is a development copy of the production site at `erp.egc-me.com`.

Every bench command must go through the serialised wrapper, because several agents/sessions
may share the one bench and one site:

```bash
scripts/bench.sh --site dev.localhost migrate
```

It holds a mutex around `docker exec … bench`, so two concurrent `bench migrate` runs can
never interleave DDL or the patch log.

## Non-negotiable invariants

Enforced by code — you will get a `ValidationError`, not a silent wrong answer:

- **ERPNext `Project` is canonical.** There is no EGC project master. Every EGC record carries
  a `project` Link, which is also how standard Frappe User Permissions cascade to this app.
- **Project isolation is server-side.** A record from Project A can never be linked into
  Project B. The shared checks live in `egc_projects/validators.py` — reuse them; do not
  hand-roll a filter, and never rely on a client `set_query` as the enforcement.
- **An issued revision is history.** `EGC Project Document Revision` is submittable, and its
  `file` field is deliberately *not* `allow_on_submit`, so Frappe itself makes the file of an
  issued revision unchangeable. A correction is always a new revision, never an edit.
- **One writer per derived value.** `document_control.py` is the only code that writes any
  `current_*` / `document_status` / `approval_status` / `revision_status` field;
  `submittal_control.py` is the only code that writes submittal state. If you find yourself
  setting one of those anywhere else, stop.
- **A document's `approval_status` describes only its current revision.** Rev 03 must never
  inherit Rev 02's approval. See `docs/ARCHITECTURE.md` §2.4.
- **EGC roles are additive, not standalone.** They grant access to EGC DocTypes only. An EGC
  user must also hold `Projects User` or `Projects Manager`, because every Hub endpoint gates
  on `Project` read permission. We deliberately do not add `Custom DocPerm` rows to the core
  `Project` DocType — see `docs/ARCHITECTURE.md` §4 for why.
- **No second ledger.** Project financials are read straight off the ERPNext `Project` fields
  that ERPNext/HRMS already maintain (`docs/ARCHITECTURE.md` §6). Never re-aggregate invoices.
- **Do not edit Frappe/ERPNext/HRMS core, ever.** Extend only via this app's DocTypes and
  `hooks.py`. Verify with `git status` inside `apps/frappe`, `apps/erpnext`, `apps/hrms`.
- **A "person" in this app IS a core `User` — never invent a lightweight identity doctype.**
  This exact ground has been rebuilt three times (flat fields → `EGC Person`/`EGC Organization`
  → `Contact`/`Customer` → `User` directly — see `docs/ARCHITECTURE_V2.md` §2's full account).
  Before adding any "person"/"party"/"contact" concept, check whether `User`, `Contact`,
  `Customer`, `Supplier`, or `Employee` already covers it. A `User` with no login intended is
  still `enabled: 1`, just with no password set and `send_welcome_email: 0` — **never
  `enabled: 0`**, which silently makes that User invisible to every Link search in the whole
  system (`user_query` hardcodes `enabled: 1`), including for records that already reference it.
- **A child table row's own `validate()` never fires automatically on parent save.** Confirmed
  directly against `frappe/model/document.py` — `Document._save()`'s `update_children()` only
  calls `d.db_update()` per row, never `run_method("validate")`. Any "this child row should
  always re-derive X on save" behavior needs the PARENT's own `validate` doc_event to explicitly
  loop over that child table and call the row's method itself (see
  `project_custom_fields.validate_project`'s WBS Node check and Stakeholder mirroring, both doing
  exactly this). A doctype-controller `validate()` alone on a child table is easy to write, looks
  correct, passes a casual read — and silently never runs.
- **Organization identity ≠ project role.** An org's own fixed global identity
  (`Customer.custom_organization_type` — Client/Consultant/Main Contractor/...) is a different
  concept from the project-scoped role a person holds on one job (`EGC Stakeholder Role`, via
  `EGC Project Stakeholder`/`EGC Assignment`). Never set the former to describe the latter.

## Where things live

| I want to… | Go to |
|---|---|
| change a status label | `egc_projects/constants.py` — every enum is defined once |
| add a project-isolation rule | `egc_projects/validators.py` |
| change revision or approval logic | `egc_projects/document_control.py` |
| change submittal review flow (multi-step, Ball in Court) | `egc_projects/submittal_control.py` |
| allow a new record type to link to an Activity | `egc_projects/relationships.py`, one entry in the registry |
| add a Project Hub panel | `api/hub.py` (data) + `egc_projects/public/js/egc_project_hub/` (Vue — see `EgcProjectHub.vue` + one component per tab) |
| seed a new master record / role | `install.py` — it is idempotent and reruns on every migrate |
| change what fields live on `Project` itself | `egc_projects/egc_projects/project_custom_fields.py` (Custom Fields, distributed across native Details/More Info tabs — see its own module docstring for the `insert_after` anchor discipline) |
| change Hub-side Project Information read/write | `egc_projects/egc_projects/project_profile.py` (`save_project_profile`, `add_stakeholder`/`remove_stakeholder`, `add_equipment_item`/`remove_equipment_item`, `get_person_info`, `resolve_role_user`, `get_stakeholders`) — called from `ProjectInfoTab.vue` |
| change how a person's organization resolves | `egc_projects/egc_projects/directory.py` — `resolve_organization(user)`, the Portal User (Customer/Supplier `portal_users` child table) lookup every mirroring controller shares |
| change the Directory tab / Portal Access grant-revoke | `api/directory.py` (`get_directory`, `grant_portal_access`, `revoke_portal_access`, `update_stakeholder_role`) + `DirectoryTab.vue` |
| change the generic person/org assignment on an Activity or Submittal | `egc_projects/egc_projects/assignments.py` (`EGC Assignment` — standalone doctype, many-to-many, not a child table) |
| change what counts as a stakeholder role, or add one | `install.py`'s `STAKEHOLDER_ROLES` tuple, seeds `EGC Stakeholder Role` |
| change in-app (ToDo/Notification Log) notifications | `egc_projects/egc_projects/notifications.py` |
| change email notifications | `egc_projects/egc_projects/notify_email.py` — deliberately separate from `notifications.py`, an additive second channel only, never a replacement |
| change My Open Items / Overview action items | `egc_projects/egc_projects/action_items.py` |
| change Activity schedule rollup (group Activities) | `egc_projects/egc_projects/activity_control.py` |
| add a Drawing/Document field | `egc_projects/egc_projects/doctype/egc_project_document/` + `api/documents.py` |
| change project health / financials drill-down | `api/hub.py` (`_project_health`, `get_financial_transactions`) |

## Running the test suite

```bash
scripts/bench.sh --site dev.localhost run-tests --app egc_projects
```

Tests build their own `Project` fixtures and must never depend on live site data.
Add tests next to their domain in `egc_projects/tests/`.

## Code style

- Tabs for indentation, double quotes (`ruff` is configured for it — see `pyproject.toml`).
- No comments explaining *what* the code does; only *why*, when genuinely non-obvious.
- Prefer `frappe.get_all` / `frappe.qb` over raw SQL.
- Every `@frappe.whitelist()` method validates permission on its `Project` before it reads
  anything. `validators.require_project_permission()` exists for exactly this.
---

## Build history — v1 technical changelog

This section is the technical record of how v1 was built: what each commit did, every defect
found in review, and the exact state the app was left in. `docs/ARCHITECTURE.md` is the binding
design; this is the log of building to it. Commits are listed oldest first.

### `3e7ed03` — WP-01: app foundation

- Scaffolded `egc_projects` with `bench new-app`, installed on `dev.localhost` alongside the
  existing `egc_hr`, `ksa_compliance`, `print_designer`, `hrms`, `erpnext`.
- Wrote `docs/ARCHITECTURE.md` (binding design) before any implementation.
- `egc_projects/constants.py` — every status enum (`ACTIVITY_STATUSES`, `REVISION_STATUSES`,
  `SUBMISSION_STATUSES`, `REVIEW_RESPONSES`, `LINK_PURPOSES`, `EGC_ROLES`, `FINANCIAL_ROLES`,
  …) defined once and imported everywhere; nothing re-types a status literal.
- `egc_projects/validators.py` — the shared server-side project-isolation kit:
  `validate_same_project`, `validate_unique_in_project`, `validate_unique_under_parent`,
  `validate_tree_parent`, `validate_project_not_changed_with_children`,
  `require_project_permission`.
- `install.py` — idempotent `after_install`/`after_migrate` hook seeding 4 roles
  (`EGC Project Manager`, `EGC Project Engineer`, `EGC Document Controller`,
  `EGC Project Viewer`), 4 Disciplines, 8 Document Types, 9 Submittal Types.
- `scripts/bench.sh` — a mutex-locked wrapper around `docker exec … bench`, so multiple
  concurrent implementation agents sharing one bench/site could never interleave a
  `bench migrate` or a test run.

### `c5a6038` — WP-02/03/04: masters, WBS, Activity, controlled documents

Three Sonnet agents ran in parallel with disjoint file ownership; each is reviewed below.

**Masters + `EGC WBS Node`** (WP-02)
- `EGC Discipline`, `EGC Document Type`, `EGC Submittal Type` — simple masters, `field:`
  autoname. Uses `before_naming()` (not just `validate()`) to normalise the code to uppercase,
  because Frappe's `field:` autoname reads the raw field value in `set_new_name()`, which runs
  *before* `validate()` — normalising only in `validate` would leave `name` out of sync with a
  differently-cased field value.
- `EGC WBS Node` — `NestedSet` tree, `nsm_parent_field = "parent_egc_wbs_node"`, multiple roots
  (one per project) — `validate_one_root()` is deliberately never called. `autoname:
  format:{project}-{wbs_code}`. `get_children()`/`add_node()` whitelisted tree endpoints,
  project-scoped server-side.
- **Reviewed and accepted as-is.**

**`EGC Activity`** (WP-03)
- Single self-referencing `NestedSet` DocType — `Mechanical > HVAC > Ductwork > Installation >
  MRI-01` are all the same DocType. No Sub-Activity DocType exists.
- `is_overdue(status, planned_end_date)` module-level helper — the single definition of
  "overdue" reused by the tree JS, the list JS, the Hub API, and the Activity Status Summary
  report.
- **Fixed in review** (not by the agent):
  - `get_children()`'s WBS-node filter combined with the parent filter, so filtering by WBS
    node returned nothing once a matching activity was not itself a tree root. Now: while
    drilling into a real parent, the WBS filter is dropped (its job is done); at root level, a
    WBS filter replaces the parent-is-empty filter instead of narrowing it further.
  - Children were ordered by `lft` (insertion order) instead of `sequence`; fixed to
    `order_by="sequence asc, activity_code asc"`.

**Controlled documents — `document_control.py`** (WP-04, the integrity-critical package)
- `EGC Project Document` (identity) / `EGC Project Document Revision` (`is_submittable: 1`,
  history).
- **The revision-integrity guarantee is a framework property, not application code**: `file` on
  `EGC Project Document Revision` is not `allow_on_submit`, so Frappe itself refuses to let an
  issued revision's file change. Verified live: `frappe.exceptions.UpdateAfterSubmitError`.
- `_recompute_revision_statuses()` is a **pure function of the current `docstatus=1` rows**:
  the highest `revision_seq` among them is `Issued`; every other one is `Superseded` pointing
  at it. Called identically after submit and after cancel — this single function handles the
  ordinary case, an out-of-order submit, and cancel-restores-the-previous-revision with no
  special-casing, because it only ever looks at what is *currently* true.
  `assert_engine_authorized()` guards both `validate()` (pre-submit) and
  `on_update_after_submit()` so a REST `PUT` cannot rewrite `revision_status`/`superseded_by`
  directly — only the engine's own `frappe.db.set_value()` calls (under an `ENGINE_FLAG`) may.
- `get_approval_status()` — the §2.4 "anti-conflict rule": derives strictly from the *current*
  revision's latest referencing `EGC Submittal Revision`, so an older revision's response can
  never leak onto a newer one. Degrades to `Not Submitted` via `frappe.db.table_exists()` guards
  while the (concurrently-built) submittal doctypes didn't exist yet.
- **Reviewed and accepted as-is.**

Independently verified end-to-end afterward (`scripts/verify_acceptance.py`, run against the
live site, rolled back): Rev 00 issued → current; Rev 01 issued → Rev 00 becomes `Superseded`
with its file byte-identical and `superseded_by` set; rewriting Rev 00's file after issue is
refused by the framework.

### `83616c3` — WP-05/06: submittals and the relationship layer

Two agents in parallel.

**Submittal domain — `submittal_control.py`** (WP-05)
- `EGC Submittal` (identity) / `EGC Submittal Revision` (`is_submittable: 1`, one review cycle)
  / `EGC Submittal Document Item` (child: which document revisions this cycle carries).
- Mirrors `document_control.py`'s engine pattern: `ENGINE_FLAG`, `_engine_set_submission()`
  bypassing hooks via `frappe.db.set_value()`, `assert_engine_authorized()`.
- `submit()` requires ≥1 attached document revision and every one of them must be
  `docstatus=1, revision_status=Issued` — a draft can never enter review.
- `record_response()` is **irreversible** — calling it twice on the same submission raises.
- `create_next_revision()` — allowed only when the latest submission is `Responded`; opens a
  new Draft cycle with an empty `documents` table (nothing carried forward) and the next
  sequential `revision_label`.
- After every submission-state change, `_refresh_documents()` calls
  `document_control.refresh_document_state()` for every distinct document the submission
  carries — this is what keeps a document's `approval_status` honest across the two engines.
- Verified live (see Wave B section below): a submittal's `Revise & Resubmit` on Rev 00,
  followed by `Approved` on Rev 01, leaves **both cycles visible**, Rev 00's response
  unchanged, and the document's `approval_status` tracking only the current revision.

**Relationship layer — `relationships.py` + `EGC Activity Link`** (WP-06)
- Standalone DocType (not a child table) implementing genuine many-to-many:
  `ALLOWED_LINK_DOCTYPES = {"EGC Project Document", "EGC Submittal"}` — a plain dict registry,
  so adding `EGC RFI`/`EGC MIR`/`EGC ITP` later is a one-line change with no schema change.
- `validate()` rejects any `link_doctype` outside the registry server-side (never trusts the
  client `get_query`), forces `project` from the activity (never client-supplied), and rejects
  a target whose `project` differs from the activity's.
- **Fixed in review** (not by the agent): the agent reported "Frappe has no multi-column unique
  constraint" and enforced (`activity`, `link_doctype`, `link_name`) uniqueness in `validate()`
  only. This is incorrect — `frappe.db.add_unique()` inside `on_doctype_update()` is the
  supported mechanism (ERPNext's `Bin` doctype uses exactly this for
  `item_code`+`warehouse`). Because `EGC Activity Link` is hash-named, nothing in its primary
  key stops two concurrent `add_link()` calls from racing past the `validate()`-time duplicate
  check. Added `on_doctype_update()` calling `frappe.db.add_unique(...,
  constraint_name="unique_activity_link_target")`, plus
  `patches/v1_0/add_activity_link_unique_index.py` (a `post_model_sync` patch) so a site that
  already has the table from an earlier version also gets the constraint. Verified in MariaDB:
  `SHOW INDEX` confirms the 3-column unique key exists.

### `d4aad24` — WP-07: Project Hub read API and reports

One agent hit a session limit partway through (after `hub.py`, Drawing Register and Submittal
Log, before the Activity Status Summary report and its own test module). Recovered by the lead:

- Reviewed the completed `api/hub.py` — every method gates on `require_project_permission()`
  first; `get_financials()` requires `constants.FINANCIAL_ROLES` and raises
  `frappe.PermissionError` rather than returning zeros; filters are checked against a
  per-endpoint fieldname allow-list before ever reaching a query.
- **`get_financials()` reads `total_billed_amount`, `total_purchase_cost`,
  `total_consumed_material_cost`, `total_costing_amount`, `total_billable_amount`,
  `total_sales_amount`, `estimated_costing`, `gross_margin`, `per_gross_margin` directly off
  `tabProject` with a single `frappe.db.get_value()`** — no re-aggregation of Sales/Purchase
  Invoices, Timesheets, Stock Entries or Expense Claims. `total_expense_claim` (an HRMS-added
  field, not core ERPNext) is read defensively via `frappe.get_meta("Project").has_field(...)`,
  returning `None` rather than a misleading `0` on a site without HRMS.
- Wrote the missing `EGC Activity Status Summary` report myself: rows in `lft` order with a
  per-row `indent` derived from the parent chain (so a moved activity re-indents without a
  backfill; a row whose ancestor is filtered out falls back to depth 0 instead of indenting
  under a row not in the result set).
- Verified financials against MariaDB directly: `140,400.00` billed / `2,808,000.00` sales order
  / `100%` gross margin — API output matched the raw columns exactly.
- Documented a permission-model gap discovered while writing this package: **EGC roles are
  additive, not standalone** — they grant nothing on the core `Project` DocType, so an EGC user
  also needs `Projects User`/`Projects Manager`. Deliberately not solved with `Custom DocPerm`
  rows on `Project` (would widen the upgrade surface and collide with `egc_hr`'s existing
  fixture on the same doctype).

### `e682fa4` — fix: undated records counted as overdue

A **Sonnet testing agent**, writing `test_hub_api.py` against the already-accepted `hub.py`,
found a genuine defect and correctly declined to fix it (per its mandate) or paper over it:

- `_activity_overview()`/`_submittal_overview()` counted an activity/submittal with **no**
  `planned_end_date`/`current_due_date` as overdue.
- Root cause, verified directly in `frappe/database/query.py`
  (`_should_apply_ifnull`/`_get_ifnull_fallback`): Frappe rewrites a `<` filter on a nullable
  field as `IFNULL(field, '') < value` for null-safety — and it explicitly skips that rewrite
  only for `>`/`>=` on Date fields, not for `<`. So `NULL < today()` became `'' < today()`,
  which is always true.
- This directly contradicted `egc_activity.is_overdue()` (`if not planned_end_date: return
  False`) and both reports, which already guarded correctly in Python.
- **Fix**: added an explicit `["planned_end_date", "is", "set"]` /
  `["current_due_date", "is", "set"]` filter tuple ahead of the `<` comparison in both
  aggregates.
- Added `test_undated_records_are_not_counted_overdue` as a true regression test — **verified
  it fails against the unfixed code** (`AssertionError: 2 != 1`) before confirming it passes
  with the fix. 60/60 tests green afterward.

### `5981642` — WP-08: Project Hub, workspace, and the deletion-contract fix

**Project Hub** (Vue 3 desk page, modelled on Frappe's own `workflow_builder` page pattern):
`egc_project_hub.bundle.js` → `EgcProjectHub.vue` root, one component per tab
(`OverviewTab`/`WbsTab`/`ActivitiesTab`/`SubmittalsTab`/`DrawingsTab`/`FinancialsTab`), a
`useHubRoute` composable syncing `/app/egc-project-hub/<project>/<tab>` with `frappe.get_route()`
and a `localStorage` fallback. All data via `api/hub.py`; the Hub never queries a DocType
directly and holds no business state that isn't re-derivable from the API.

The agent did real browser verification (screenshots, console, network) against ~30 live
ERPNext projects and found/fixed 4 bugs itself before reporting: `frappe.format()`/`
frappe.datetime.comment_when()` returning HTML meant for `v-html` rendered as literal markup
under plain interpolation (switched to `format_currency()`/`prettyDate()`, which return plain
strings); a global `frappe.router.on("change", …)` handler misreading *any* Desk navigation as a
Hub route change and corrupting `localStorage` (gated on `route[0] === "egc-project-hub"`); and
a null-deref race when a Link control's own change handler fired after Vue had already
unmounted it (deferred via `setTimeout(0)`).

**Reviewed live in the browser by the lead and fixed further:**
- Financials tab showed bare numbers with no currency indicator, because this site's `SAR`
  Currency record has a single-space `symbol` — added an explicit "All amounts in {currency}"
  caption above the grid rather than trusting the symbol.
- The Activities register showed raw WBS record names (`PRJ2601050-01.02.01.01`) instead of a
  readable label. Added `_wbs_labels()` to `hub.get_activities()` (one batched query, not
  N+1) returning `"01.02.01 HVAC"`-style labels, and made the cell a deep link.

**Deletion contract redefined** (a deliberate spec change, flagged for the user to veto):
previously "only Draft is deletable, Cancelled/Issued rows stay" for both
`EGC Project Document Revision` and `EGC Submittal Revision`. Changed to: Draft freely
deletable; Issued/Submitted (`docstatus=1`) **never** deletable, cancel first; Cancelled
(`docstatus=2`) deletable **by a System Manager only**. Rationale: Frappe's own permission
model would otherwise let *anyone* who can delete the doctype also delete a cancelled document,
which would let a document controller erase history simply by cancelling a revision first —
requiring cancellation *and* an administrator makes a purge a deliberate, auditable act while
still leaving a real escape hatch (a record nobody can ever remove is its own liability). Tests
for both doctypes were rewritten to assert the new two-tier rule, including a
`_make_user()`-scoped negative case proving a Document Controller is denied the purge.

Also added: `egc_projects/egc_projects/workspace/egc_projects/egc_projects.json` (the app's
Desk entry point — shortcuts to the Hub/Activities/Drawing Register/Submittal Log, cards for
every doctype grouped by domain), and `egc_projects/demo.py`
(`bench execute egc_projects.demo.seed` / `.purge`) — a reproducible, fully-reversible dataset
implementing the build brief's own WBS/Activity/Drawing/Submittal acceptance scenarios, so the
app can be explored without hand-building fixtures.

### `6415706` — fix: report client scripts

Discovered while independently re-verifying WP-07's reports in the browser: the Drawing
Register's and Submittal Log's `formatter()` callbacks dereferenced `data.<field>` without a
null check. Frappe's datatable calls the formatter for placeholder/total rows that carry no
`data` object; the resulting throw silently blanked the entire table in some render paths.
Added an `if (!data) return value;` guard to both, and normalised each report's `Select` filter
`options` to a newline-joined string (the shape the Select control actually expects) instead of
a raw JS array.

## Independent verification performed by the lead (not the implementing agents)

- `scripts/verify_acceptance.py` — scripted, rolled-back walk of acceptance Scenarios 4–5
  against the live site (see WP-04 above).
- `egc_projects/demo.py seed()` — real records for Scenarios 2, 3, and 6 (a 4-level WBS tree; a
  6-node Activity tree using one DocType recursively; one Drawing and one Submittal each linked
  to 3/2 Activities respectively with no duplication), plus explicit cross-project rejection
  checks (`ValidationError` on a cross-project WBS parent, `LinkValidationError` on a
  cross-project Activity Link target).
- Financials cross-checked against `mysql … SHOW COLUMNS`/direct `SELECT` on `tabProject`, not
  merely against the app's own tests.
- Browser verification of the Hub (all 6 tabs), the native `EGC Activity` tree view, the
  `EGC Drawing Register` report, the `EGC Projects` workspace, and the ERPNext `Project` form's
  "Open in EGC Projects" entry point — screenshots, `read_console_messages`, and
  `read_network_requests` were all inspected, not just "it rendered."
- `git status` on `apps/frappe`, `apps/erpnext`, `apps/hrms` after every wave — 0 changed files
  throughout.
- Two consecutive `bench migrate` runs confirmed idempotent (no duplicate masters/roles).

## Final state (v1)

- **10 DocTypes**: `EGC Discipline`, `EGC Document Type`, `EGC Submittal Type`, `EGC WBS Node`,
  `EGC Activity`, `EGC Project Document`, `EGC Project Document Revision`, `EGC Submittal`,
  `EGC Submittal Revision`, `EGC Submittal Document Item`, `EGC Activity Link` (11, including
  the link doctype).
- **3 script reports**: `EGC Drawing Register`, `EGC Submittal Log`, `EGC Activity Status
  Summary`.
- **1 Desk Page** (`egc-project-hub`, Vue 3) + **1 Workspace** (`EGC Projects`).
- **62 tests, all green** (`test_wbs.py`, `test_activity.py`, `test_document_control.py`,
  `test_submittal.py`, `test_relationships.py`, `test_hub_api.py`).
- `bench migrate` clean and idempotent; `frappe`/`erpnext`/`hrms` unmodified throughout.
- No core Frappe/ERPNext/HRMS modification at any point — confirmed by `git status`, not by
  assumption.

## Build history — v2 technical changelog

v2 is the "Procore-Level Functional & UX Upgrade" — an additive, backward-compatible deepening
of v1, not a rewrite (docs/ARCHITECTURE_V2.md is the binding spec). Built entirely by direct work
in this bench (no Sonnet sub-agent delegation past Wave A — four consecutive sub-agents hit
session-limit failures on Wave B, and the work continued directly from that point on).

### `9131870` — Wave A: Project Information, Documents tool, Hub shell/header redesign

Project Profile/Stakeholders doctype and API, healthcare-context fields, the Hub's redesigned
header/shell, and the Documents tab's promotion to a full detail workspace.

### `f07bd77` / `56ef0d1` — Wave B: Activity schedule, parent rollup, dependencies

`activity_control.py` (new engine module): `refresh_activity_rollup`/`refresh_ancestors` derive a
group Activity's dates/duration/status/progress from its direct children only, bottom-up, on
every child write — never independently stored. `EGC Activity Dependency` (predecessor/successor,
cycle-checked via BFS, composite-unique-indexed). `ActivityDetail.vue` — full detail drawer
(schedule, dependencies with add/remove, children, linked Submittals/Documents, history).
`duration_days` writes `0` rather than `None` when dates are missing — `frappe.db.set_value`
skips the `cint(None)→0` coercion a normal `doc.save()` gets, and the column is `NOT NULL DEFAULT
0`, so a bare `None` throws `IntegrityError`. 10 + 12 new tests.

### `aeb9252` — Wave B: WBS operational upgrade

`api/wbs.py`: subtree-wide rollups (`get_wbs_summary`, O(n²) over the NestedSet lft/rgt
containment, deliberate for simplicity at this scale), `reorder_wbs_nodes`, `copy_wbs_branch`,
`bulk_create_wbs_nodes` (abort-on-first-error with manual cleanup — Frappe's own request-level
rollback only applies to real HTTP calls, not direct-Python test calls). `WbsTreeNode.vue` gains
rollup metrics, reorder, and quick-add; the Bulk Add dialog was rewritten to match ERPNext's own
native `frappe.ui.Dialog` + `Table` pattern (`task_tree.js`'s "Add Multiple Tasks") rather than a
bespoke Vue modal. Found and fixed live: `reorder_wbs_nodes`/`bulk_create_wbs_nodes` 500'd on
every real browser call — Frappe v16's whitelist arg validation uses Pydantic's
`validate_python`, not `validate_json`, so a `list[...]`/`dict[...]` type hint rejects the
JSON-encoded string a real HTTP call actually sends; fixed by leaving the param untyped and
calling `frappe.parse_json()` manually. Regression tests added for both endpoints.

### `eea04c5` / `04ee06b` — Wave C: Submittal review workflows, Ball in Court, notifications

`EGC Submittal Workflow Template` (+ step child table) and `EGC Submittal Review Step` (a
standalone hash-named doctype, not a child table — steps need independent ToDo assignment and
identity-based authorization). `submittal_control.py` gains a ~375-line v2 section on top of the
untouched v1 lifecycle: steps sharing a `sequence` form a parallel stage; a stage advances only
once every *required* step at that stage has responded; a single Revise & Resubmit/Rejected from
*any* reviewer ends the whole submission immediately without waiting on siblings; an optional step
still open when its stage clears is marked Skipped, not left dangling. `record_step_response`'s
authorization is identity-based (`reviewer_user`, or an internal override role), not
doctype-permission-based, since a reviewer may be an external party holding no EGC role at all.
Ball in Court is never stored independently — always derived live from `In Review` step rows, then
copied onto the submission/Submittal for display. `notifications.py` (new) rides
`frappe.desk.form.assign_to` for delivery and `notification_log.enqueue_create_notification` for
the daily due-date reminder scheduled task, baking the date into the dedupe key so it actually
recurs. `SubmittalDetail.vue` (new) — the full detail workspace: workflow timeline, apply-template,
submit/respond, documents, submission history, linked activities.

Bugs found via genuine multi-step live browser testing (not caught by the 130+ unit tests, which
asserted the engine's own field writes rather than what the UI actually reads):
- `_evaluate_stage` checked "any required step still open?" *before* checking for a blocking
  terminal response, so a lone Revise & Resubmit/Rejected didn't end the submission while a
  sibling required step was still `In Review`. Reordered so the blocking check always runs first.
- A brand-new Submittal (zero submissions) had no path in the Hub to create its first submission
  cycle — the entire "Current Submission" section was gated on one already existing. Added
  `create_first_submission` (deliberately distinct from `create_next_revision`, whose "only after
  Responded" contract is unchanged) and an empty-state action in the drawer.
- `SubmittalDetail.vue`'s `can_respond_to()` only showed the Respond button for the exact
  `reviewer_user`, never for an internal override role, even though the backend already
  authorizes it — an admin covering for an external reviewer had no UI path. It also required
  `canWrite` even for the assigned reviewer's own step, breaking the documented external-reviewer
  case entirely. Fixed to mirror the backend's override role set exactly.
- `_refresh_ball_in_court` wrote only the submission's own `ball_in_court_label`, never
  propagating to the parent Submittal's `ball_in_court` — the field the Hub register and drawer
  header actually display. `refresh_submittal_state` was wired only into terminal/lifecycle paths,
  so a mid-workflow stage advance left the header showing the *previous* stage's reviewer until
  the whole submission resolved. Fixed by propagating on every Ball in Court recompute; covered by
  a regression test asserting the Submittal's field changes mid-workflow, not just at the end.

### Wave D: Drawing Sets/Areas and publish readiness

`EGC Drawing Set`/`EGC Drawing Area` (new, project-scoped, flat — deliberately not a tree, and
not the future full Project Location hierarchy). New fields on `EGC Project Document`
(`drawing_set`, `drawing_area`, `drawing_date`, `received_date`, same-project validated) and on
`EGC Project Document Revision` (`readiness`: Uploaded/Reviewed/Ready to Publish — internal
pre-issue metadata only; `submit()` remains the one and only act of publishing, `readiness` adds
no new lifecycle state and is not `allow_on_submit`, so the framework itself locks it once
Issued). `api/documents.py` gains `update_revision_readiness` (own endpoint, since `readiness`
can change repeatedly before a Draft revision is ever issued, unlike the create-once fields).
`get_document_detail` gains an `is_drawing` flag (looked up from `document_type`) so
`DocumentDetail.vue` shows the Drawing metadata block and the readiness column only for
documents whose type is actually flagged as a drawing — reused as the drawing detail workspace
rather than building a parallel component, per "a Drawing is a Document with drawing-specific
semantics." `DrawingsTab.vue`/`EGC Drawing Register` both gain Set/Area columns and filters.
12 new tests (`test_drawings.py`).

### Wave E: Financials drill-down, Project health, My Open Items

`api/hub.py.get_financial_transactions(project, metric)` — for each of the six metrics with a
well-defined underlying transaction set (billed/purchase_cost/expense_claims/
consumed_material_cost/timesheet_cost/sales_order_value), hand-reconstructs the EXACT query
ERPNext/HRMS uses to arrive at the matching `get_financials()` figure (read straight from
`erpnext.projects.doctype.project.project.Project`/`hrms.overrides.employee_project.
EmployeeProject`, which is what this site's Project class is actually overridden to — that's why
`timesheet_cost` sums `costing_amount` not `base_costing_amount`, and why `expense_claims`
exists at all). Never recomputes the total independently, so the drill-down and the headline
figure can never disagree; verified live against real seeded transactions, not just fixtures.
`FinancialsTab.vue`'s six reconcilable tiles are now clickable, opening a dialog of the
underlying documents with links to their native forms.

`_project_health()` in `api/hub.py`, folded into `get_overview()`'s response — exactly the four
signals docs/ARCHITECTURE_V2.md §11 specifies (schedule/submittals/documents/financials, each
green/orange/red) and no more, per the brief's own "only derive health where the rules are
defensible" caution. `_drawings_health()` reuses `document_control.get_approval_status()`'s exact
query (latest non-cancelled submission carrying a document's current revision) to find the
governing due date, rather than a different, possibly-disagreeing lookup.

`egc_projects/action_items.py` (new) — `get_open_items_for_user(user, project=None)`, a plain
registry (not a generic framework) combining `EGC Submittal Review Step` (reviewer_user=user,
In Review) and overdue `EGC Activity` (responsible_user=user) into one normalised shape; adding
a future source is a new function plus one line here, not a schema change. Exposed as
`api/hub.py.get_my_open_items`, surfaced as a card on `OverviewTab.vue`.

10 new tests (`test_financial_transactions.py`) plus 12 more in `test_hub_api.py`
(health + My Open Items); full suite at 161.

### Post-Wave-E: user-directed rework — Project Information relocation and shell redesign

Two changes driven directly by explicit user feedback on the shipped v2 Hub, not from the
brief's own Wave plan:

**Project Information moved off a satellite doctype onto `Project` itself as Custom Fields.**
Full rationale in `docs/ARCHITECTURE_V2.md` §1 — the short version: v1's own `EGC Project
Profile` doctype was built on an unverified assumption that Custom Fields on `Project` would
collide with `egc_hr`'s. They don't (`egc_hr` already extends `Project` with `custom_egc_*`
fields the exact same way), and the satellite doctype meant Project Information was edited
through a bespoke Hub-side Vue form instead of the *native* `Project` form — which is exactly
where `egc_hr`'s own Supervisors/Project Location fields already live. `project_custom_fields.py`
(new) defines the whole field set under one `Tab Break` ("EGC Project Info"); `ProjectInfoTab.vue`
is now read-only with a link out to the native form. `EGC Project Profile` doctype deleted
entirely (one near-empty demo row migrated, not lost).

**The Hub's shell was rebuilt as a sidebar-navigated independent app, replacing the horizontal
tab bar.** The old shell — a boxed header card + a Bootstrap-style tab strip, all sitting inside
Desk's own page-head/breadcrumb bar — read as "a themed DocType view," not a distinct tool. Now:
`egc_project_hub.js` calls `wrapper.page.page_head.hide()` (the same technique Print Designer
uses, `frappe.ui.pages["print-designer"]`) so the Hub owns the entire content area below Desk's
navbar. `HubSidebar.vue` (new) is a persistent left icon rail — Procore's own "tool switcher"
pattern — replacing `TabNav.vue` (deleted), with the project switcher and brand mark folded into
it too (project switching is a navigation act, not header identity). `HubHeader.vue` shrank to a
single-row top bar (name/status/stage/dates/progress/actions only — no more project switcher, no
more stakeholder chips, both redundant with the sidebar/Project Info tool). New `--egc-*` CSS
tokens for the shell chrome are aliased to Frappe's own existing semantic variables
(`--control-bg`, `--border-color`, `--primary`, ...) rather than a hand-rolled parallel palette,
so the shell tracks Desk's light/dark theme automatically — verified live in both. Below ~900px
the sidebar becomes an off-canvas drawer behind a hamburger button (`HubSidebar.vue`'s own
`@media` block) rather than staying a fixed 232px column that would eat most of a phone screen.

Two real layout bugs found and fixed via live browser + DOM introspection while building this,
not caught by eyeballing alone: (1) a `margin: calc(-1 * var(--page-head-height))` meant to
reclaim the hidden page-head's space applied to *all four sides* via shorthand, shoving the
whole shell 48px left as well as up — removed; `page_head.hide()` already leaves no gap to
reclaim. (2) `.egc-shell { height: calc(100vh - var(--navbar-height)) }` double-subtracted the
navbar height — `.layout-main-section` (the Hub's own mount point) is already sized by Frappe's
own layout CSS to exactly the space available below Desk's chrome, navbar included, whether or
not a navbar is actually visible in a given runtime (traced via `getComputedStyle`/
`getBoundingClientRect` on every ancestor up to `#body` to confirm) — fixed to `height: 100%`.

No backend changes in this pass — `docs/ARCHITECTURE_V2.md` §1-§4 rewritten to match the new
Project Information model; full suite still 161 (9 of which moved from `test_project_profile.py`
to `test_project_info.py`, testing the new field-based model instead of the deleted doctype).

## Build history — v3 technical changelog

v3 is "Level 0"/"Level 1" of the project-controls expansion, plus a same-session correction
cycle on the Directory/identity model driven directly by user feedback rather than a written
brief. `docs/ARCHITECTURE_V2.md` §2 carries the full technical account of the identity model's
three rebuilds; this section is the commit-level record of how it happened and what else shipped
alongside it.

### Level 0 — "Project Directory Must Be Used Everywhere," multi-assignment, Hub notifications

Introduced `EGC Person`/`EGC Organization` as dedicated Directory doctypes (reasoning at the
time: a person/org referenced from Stakeholder, `EGC Assignment`, a Submittal's
`received_from_person`, and a Document's `originator_person` needed one canonical record, not
four independent copies). `EGC Assignment` (new, standalone) — the generic multi-person/
multi-organization relationship replacing `EGC Activity`'s old single `responsible_user`/
`responsible_supplier` fields, extended to also carry `EGC Submittal`'s reviewers/team.
`api/directory.py` + `DirectoryTab.vue` — the Hub's Directory tab, and Portal Access grant/revoke
(the same `EGC External Viewer` + `User Permission` pattern `test_external_viewer.py` already
proved out, now reachable from the Hub). Discovered mid-build and documented directly in
`api/directory.py`'s own module docstring: a client-side submittal reviewer is not a separate
access tier from a viewer — `record_step_response` authorizes purely by identity, not doctype
permission, so a planned "External Reviewer" role was dropped once the actual authorization code
was read rather than assumed. `notify_email.py` (new) added email as a genuinely additive second
channel on top of `notifications.py`'s existing in-app-only delivery — two events (review
requested, Directory welcome) reach an inbox, kept deliberately simple (plain text, no
`Email Template` doctype).

Also this phase: `Project`'s own Details/More Info tabs cleaned up (hid ~15 core fields this app
never used — `actual_start_date`, `is_active`, the whole `collect_progress` email-schedule
cluster, etc. — via Property Setter, never deleted, reversible); a real `custom_project_address`
Link to core `Address` replacing five flat country/region/city/address/time-zone fields, wired
through the standard `Dynamic Link` mechanism; `percent_complete_method`'s options trimmed to
`Manual`/`Activity Completion` (the two this app actually uses); the Hub's `"Open in EGC
Projects"` button and its redundant dropdown (WBS/Activities/Drawing Register/Submittal Log —
all already reachable as Hub tabs) trimmed to one clean entry point.

**A real mistake, caught by direct user feedback and fixed the same day:** the field-hiding pass
above hid `sales_order`/`department`/`cost_center` on the reasoning "nothing in this app's own
code reads them" — which is not the same claim as "nobody uses them." The user links Sales
Orders to Projects directly via native ERPNext workflows entirely independent of what this app's
own code queries. *"did you remove sales orders being linked to projects?? are we acting
stupid??"* — all three un-hidden, plus a `_unhide_previously_hidden_project_fields()` cleanup so
a site that had already run the flawed version self-heals on the next migrate, not just future
installs. **Lesson generalized into the invariants above:** "no code reference" is never
sufficient grounds to hide/remove a native field — verify it isn't used through a path this app's
own code doesn't touch.

### Level 1 — Submittal architecture redesign

A full rebuild of the Submittals UX around explicit, user-set rules (recorded verbatim in
project memory, not this file, since they're behavioral/product rules rather than technical
architecture — see rules like "a Submittal is by definition a formal review/approval process,"
"submitted history is permanent, no delete/bypass," "one Submittal revision can carry multiple
Document Revisions," "never make someone pick a Document Revision directly when starting a
submission," "a resubmission must feel like continuing the same submittal, not starting a new
one"). Technical highlights: `SubmittalDetail.vue` rebuilt as a full-page view (not a side
drawer — explicit user preference, "I don't want a side bar I want to have a full screen thing")
with one merged chronological timeline (state changes and comments interleaved by real
timestamp, GitHub-PR-style) instead of separate boxes per review cycle; `EGC Project Document`/
`EGC Submittal` gained the Directory-linked `originator_person`/`received_from_person`/
`responsible_organization` fields (§2 of the v2 addendum) so "who/what org" on a document or
submittal is a real link, not free text, everywhere it appears — the free-text field remains
only as a controlled fallback for a genuine one-off party.

### 2026-08-30 — the identity model rebuilt twice in one session

Starting point: the user's review of the shipped work above escalated into a full audit —
*"why do we need EGC Person doctype? Why? I don't believe we need that, you can just use the
user doctype."* Research-verified (not guessed) that `EGC Person`/`EGC Organization` were
themselves reinventions of core `Contact`/`Customer`, and that Project Code
(`custom_egc_project_code`) was a second, disconnected identity field alongside `Project`'s own
`PROJ-.####` naming series. First pass replaced `EGC Person`/`EGC Organization` with `Contact`/
`Customer` (association via `Contact.links`, the same Dynamic Link mechanism already used for
`custom_project_address`); dropped Project Code entirely; folded the three flat Site Contact
fields into the Directory as a new "Site Contact" stakeholder role.

**The user rejected the Contact-based design too**, and specified the actual target directly:
*"the directory needs the people in it to be users... the user itself is linked with the
customer using the Customer Portal User child table in Customer Doctype... or linked with the
supplier, if not linked then he is a EGC Internal user."* Second pass: every `person` field
(`EGC Project Stakeholder`, `EGC Assignment`, `EGC Submittal.received_from_person`,
`EGC Project Document.originator_person`) repointed straight at `User`; `organization` on
Stakeholder/Assignment became a Dynamic Link (`Customer` or `Supplier`) resolved via
`directory.resolve_organization()`, reading ERPNext's own native `Portal User` child table
(`portal_users`, already on both `Customer` and `Supplier` — no join table invented). `Contact`
is now absent from this app's code entirely.

Two genuine, previously-invisible Frappe bugs surfaced and fixed while wiring this up, both
generalized into standing rules in the invariants section above:
- **A child table row's own `validate()` never fires on parent save** — confirmed directly
  against `frappe/model/document.py`. `EGCProjectStakeholder.fetch_from_person()` had silently
  never executed via a plain native-form edit, in any version of this doctype, ever — only
  `project_profile.add_stakeholder`'s own API-layer pre-fill (which exists for an unrelated
  reason, `party_name`'s `reqd` check) ever exercised the mirroring logic. Fixed by having
  `project_custom_fields.validate_project` (already doing the same workaround for the WBS Node
  check) explicitly loop over stakeholder rows and call `fetch_from_person()` on each.
- **A Dynamic Link's own existence check (`_validate_links()`) runs before a row's `validate()`
  can set anything** — same ordering trap, different mechanism. `organization_type` needed a
  field-level `"default"` (evaluated at row-construction time), not a controller-side default.

**A live UX gap caught by direct user feedback, twice in a row:**
1. Every "Add Person" dialog's own description text promised "auto-fill the fields below," but
   the auto-fill only ever happened server-side, invisible until after the dialog closed —
   *"what are we doing man."* Fixed with a shared whitelisted preview endpoint
   (`project_profile.get_person_info`) wired as a `change` callback (the field-def property
   Frappe's `base_control.js` actually dispatches — `me.df.change || me.df.onchange`, confirmed
   against source) on the Person field of all 5 affected dialogs.
2. The same dialogs let a PM pick someone already on the project's Directory, creating a
   duplicate row — *"it shouldn't show me the users that are already in the directory."* Fixed
   by filtering the Person Link's own `get_query` against the already-loaded stakeholder list
   (client-side, no new endpoint) — scoped to the two Directory-adding dialogs only, since the
   same person legitimately holding two different roles on one Activity/Submittal is a separate,
   valid, already-tested case.

Also caught mid-build: two demo Users created `enabled: 0` on the wrong assumption that "no
login intended" meant disabled — Frappe's default `User` Link search hardcodes `enabled: 1`, so
a disabled User silently disappears from every Person picker in the app. Re-enabled; generalized
into the invariant above.

Full suite green (320 tests) after every step in this sequence — commit-by-commit, never one
giant batch. `docs/ARCHITECTURE_V2.md` §1/§2/§4/§7 rewritten to match; this file's "Where things
live" table and invariants updated in the same pass.
