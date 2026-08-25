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
- **No second ledger.** Project financials are read straight off the ERPNext `Project` fields
  that ERPNext/HRMS already maintain (`docs/ARCHITECTURE.md` §6). Never re-aggregate invoices.
- **Do not edit Frappe/ERPNext/HRMS core, ever.** Extend only via this app's DocTypes and
  `hooks.py`. Verify with `git status` inside `apps/frappe`, `apps/erpnext`, `apps/hrms`.

## Where things live

| I want to… | Go to |
|---|---|
| change a status label | `egc_projects/constants.py` — every enum is defined once |
| add a project-isolation rule | `egc_projects/validators.py` |
| change revision or approval logic | `egc_projects/document_control.py` |
| change submittal review flow | `egc_projects/submittal_control.py` |
| allow a new record type to link to an Activity | `egc_projects/relationships.py`, one entry in the registry |
| add a Project Hub panel | `api/hub.py` (data) + `egc_projects/page/egc_project_hub/` (Vue) |
| seed a new master record | `install.py` — it is idempotent and reruns on every migrate |

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
