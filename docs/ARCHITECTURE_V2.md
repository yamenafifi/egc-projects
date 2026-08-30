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

## 1. Project Information — Custom Fields on `Project`, revised from v1's own design

**Superseded decision, and why.** V1 originally chose a 1:1 satellite DocType
(`EGC Project Profile`), reasoning that Custom Fields on core `Project` "would collide with
`egc_hr`'s existing `custom_egc_*` fields." Live investigation while building this section
proved that reasoning wrong: `egc_hr` already extends `Project` with its own Custom Fields
(`custom_egc_supervisors_section`/`custom_egc_supervisors`, plus a pre-existing production set —
`custom_project_location`/`custom_latitude`/`custom_longitude`/`custom_geofence_radius`/
`custom_site_coordinates_dms`, predating `egc_hr` itself, which its own
`setup/bootstrap_custom_fields.py` deliberately does not redefine — see that file's comment),
and Frappe's own `insert_after`-chained Custom Field model composes two apps' fields on the same
doctype without conflict as long as fieldnames are namespaced and neither app assumes it owns
the field immediately before/after its own. There was never a real collision risk — only an
unverified assumption.

More importantly: a satellite DocType meant Project Information was **edited through a bespoke
Hub-side form** (`get_project_profile`/`save_project_profile`, a custom Vue editor) — which
reads, to anyone used to how `egc_hr`'s own Supervisors/Project Location fields already work on
the *native* `Project` form, like the Hub re-implementing a worse version of a form Frappe
already provides for free. **Project Information now lives directly on `Project` as Custom
Fields** (`egc_projects/egc_projects/project_custom_fields.py`), edited on the native `Project`
form's own **"EGC Project Info" tab** — the same place, the same mechanism, as `egc_hr`'s
fields. The Hub still has a "Project Details" view, but it is now **read-only**: a curated
summary with a link out to the native form, never a second place the same data can be edited.

Do not duplicate a field ERPNext `Project` (or `egc_hr`) already owns. Specifically **not**
duplicated: `expected_start_date`/`expected_end_date`, `actual_start_date`/`actual_end_date`,
`status`, `project_type`, `customer` (= Client — see §2), and — critically — **latitude/
longitude/geofencing**, which is `egc_hr`'s Project Location section's job, not this app's.
(v1's field list included its own `latitude`/`longitude` in the satellite doctype; that was
itself an undetected duplicate of the pre-existing production fields, caught and dropped during
this migration, not carried forward.)

> **2026-08-30 revision (superseding the rest of this section as originally written):** the
> single dedicated "EGC Project Info" Tab Break described below was removed in a later,
> user-directed pass ("Do not force routine Project setup through the raw ERPNext Project form"
> — Level 0 §8) — routine editing moved to the Hub itself (`project_profile.py`'s
> `save_project_profile`/`add_stakeholder`/etc., called from `ProjectInfoTab.vue`, which is
> **editable**, not read-only as originally stated here). The fields still live on `Project` as
> Custom Fields (`project_custom_fields.py`), just distributed across the **native Details and
> More Info tabs** (via `insert_after` anchors, not one dedicated tab) so the native form still
> works as a secondary path — see that file's own module docstring for the exact anchor
> discipline (including the `custom_egc_details_bridge`/`custom_egc_more_info_bridge` workaround
> for a `Meta.sort_fields()` quirk). Three further, more recent revisions on top of that:
>
> - **`custom_egc_project_code` was dropped entirely** (not hidden — deleted from
>   `CUSTOM_FIELDS`, moved to `_RETIRED_FIELDS`). It was a second, manually-typed identity
>   field with no relationship to `Project`'s own `PROJ-.####` naming series, which stays the
>   sole identity and is untouched.
> - **The flat `custom_egc_country`/`_region`/`_city`/`_address`/`_time_zone` fields were
>   dropped**, replaced by a single `custom_project_address` (Link → core `Address`), linked via
>   the standard `Dynamic Link` mechanism (`project_profile.ensure_address_linked_to_project`) —
>   one real Address record shared with the rest of ERPNext, not five unstructured strings.
>   `egc_hr`'s own GPS/geofence Project Location fields are untouched and still distinct from
>   this postal address.
> - **The three flat Site Contact fields were dropped**, folded into the Directory instead (a
>   Stakeholder row with the "Site Contact" role — see §2) rather than a fourth parallel identity
>   mechanism, per direct user feedback ("the site contact should be a CRM linked thing").
>
> `custom_egc_work_scope` and `custom_egc_contract_value` were also dropped in this same
> revision — scope lives in Activities/WBS, not a freeform rich-text duplicate; contract value is
> covered by core `total_sales_amount` plus `EGC Change Order` (see `api/change_orders.py`), so a
> second, unsynced number would only contradict it.

### Fields — `custom_egc_*` Custom Fields on `Project`, distributed across the native Details/More Info tabs

Placement (see `project_custom_fields.py` for the exact `insert_after` chain): Classification,
Description, and Contract Dates land at the end of the Details tab; Stakeholders, Address, and
Healthcare/Equipment land at the end of More Info, after `notes` (and after `egc_hr`'s own
Supervisors table).

**Classification**
- `custom_egc_project_stage` (Select: `Design`, `Procurement`, `Construction`, `Commissioning`,
  `Closeout`, `Warranty`) — a construction-lifecycle stage, a different axis from core
  `Project.status` (Open/Completed/Cancelled/On Hold).
- `custom_egc_sector` (Select: `Healthcare`, `Industrial`, `Commercial`, `Infrastructure`,
  `Other`).
- `custom_egc_delivery_method` (Select: `Design-Bid-Build`, `Design-Build`, `EPC`, `Turnkey`,
  `Other`).
- `custom_egc_contract_type` (Select: `Lump Sum`, `Unit Price`, `Cost Plus`, `Time & Material`,
  `Other`).

**Description**
- `custom_egc_project_description` (Small Text), `custom_egc_project_image` (Attach Image).

**Stakeholders** — Table field `custom_egc_stakeholders` (`EGC Project Stakeholder`), see §2.

**Address** — `custom_project_address` (Link → core `Address`), see the revision note above.

**Healthcare / Equipment** — Table field `custom_egc_equipment_items`
(`EGC Project Equipment Item`), see §3. Deliberately a *child table*, not singular fields,
because the v1 brief's own example (`Radiology Department > MRI-01, MRI-02, CT-01`) already
implies multiple pieces of equipment per project.

**Contract Dates** — only what core `Project` doesn't already carry: `custom_egc_contract_date`,
`custom_egc_forecast_completion_date`, `custom_egc_warranty_start_date`,
`custom_egc_dlp_end_date`.

### Validation
- `Project`'s `validate` doc_event (`hooks.py` → `project_custom_fields.validate_project`,
  since `Project` is core and can't carry its own `validate()` override) checks every
  Healthcare/Equipment row's `wbs_node` belongs to the same project, via the existing
  `validators.validate_same_project` helper — no new validation pattern invented, same rule v1
  had, just relocated from a doctype-controller `validate()` to a hook. This same hook is also
  where `EGC Project Stakeholder.fetch_from_person()` gets explicitly called per row — see §2's
  own note on why that can't just be a doctype-controller `validate()`.

---

## 2. Stakeholders and the Directory — identity is the User, not a satellite doctype

> **This section has been rewritten twice since v2 originally shipped, and is the single most
> important piece of this document for a future contributor to get right — this exact ground has
> been re-invented from scratch three times in this app's history.** The full story, in order:
>
> 1. **v2 original (this section as first written):** a flat `party_name`/`organization`
>    (Data)/`user`/`contact` (Link `Contact`) shape directly on `EGC Project Stakeholder`, no
>    dedicated identity doctype.
> 2. **Level 0 (project-controls expansion, "Project Directory Must Be Used Everywhere"):**
>    introduced `EGC Person`/`EGC Organization` as reusable, dedicated Directory doctypes,
>    referenced from Stakeholder/`EGC Assignment`/`EGC Project Document.originator_person`/
>    `EGC Submittal.received_from_person` — reasoning: a person/org referenced from multiple
>    places needed one canonical record, not five copies.
> 3. **2026-08-30, corrected twice in one session, after direct user pushback:** `EGC Person` and
>    `EGC Organization` were themselves reinventions of primitives Frappe/ERPNext already ship —
>    core `Contact` and `Customer`. First correction replaced them with `Contact`/`Customer`. The
>    user rejected that too — *"the directory needs the people in it to be users"* — Contact was
>    still the wrong abstraction for a system where "is this person a Directory entry" and "does
>    this person have a Hub login" are the same question. **Final, current state:** `person`
>    fields link directly to core `User`. No separate identity doctype exists at all.
>
> **The lesson, stated as a standing rule, not just history:** before adding any kind of
> "person"/"organization"/"contact" concept to this app, check whether core Frappe/ERPNext
> already models it (`User`, `Contact`, `Customer`, `Supplier`, `Employee`) — and if the concept
> is "a person who may or may not have a login," the answer is `User` directly (a `User` can
> exist `enabled: 1` with no password and no `send_welcome_email` — a fully valid, non-logging-in
> identity — never a separate "lightweight person" doctype).

`EGC Stakeholder Role` — small master (mirrors `EGC Discipline`): `role_name` (unique),
`is_egc_internal` (Check — distinguishes an EGC staff role from an external party role, purely a
display/filter flag now, not a resolution mechanism — see below), `enabled`, `sequence`.

Seeded (idempotent, in `install.py`, `STAKEHOLDER_ROLES`): `Client`, `Client Representative`,
`Site Contact` (folds the old flat Site Contact fields into the Directory, §1), `Main Contractor`,
`Consultant`, `Architect`, `OEM`, `OEM Engineer`, `Subcontractor Engineer`,
`Supplier Representative`, plus the internal roles `EGC Project Manager`, `EGC Site Manager`,
`Project Superintendent`, `Office Engineer`, `Project Engineer`, `Document Controller`, `QA/QC`,
`HSE`, `Commercial`, `Quantity Surveyor`.

### `EGC Project Stakeholder` — child table on `Project` (`custom_egc_stakeholders`)

- `role` (Link `EGC Stakeholder Role`, reqd).
- `person` (Link **`User`**, optional) — the normal path. Links this row directly to a User;
  their login IS their identity here, no separate record to keep in sync.
- `party_name` (Data, reqd) — mirrors `person`'s `full_name` once `person` is set; stays
  independently typed **only** for a genuine one-off party with no User yet (Frappe's own
  "controlled free-text fallback").
- `organization_type` (Select: `Customer`/`Supplier`, hidden, field-defaults to `Customer`) +
  `organization` (**Dynamic Link**, `options: organization_type`) — see "Organization
  resolution" below for how this gets filled.
- `email`/`phone` (Data) — mirror `person`'s `User.email`/`User.phone` (falling back to
  `mobile_no`) once `person` is set.
- `is_primary` (Check).

**Mirroring discipline:** once `person` is set, `party_name`/`organization_type`/`organization`/
`email`/`phone` **always** re-derive from the live `User` record on every save, never drift into
an independent copy — the free-text fields stay directly editable only when `person` is blank.
This is implemented in `EGCProjectStakeholder.fetch_from_person()` (the child doctype's own
`validate()`) — **but Frappe never dispatches a child table row's own `validate()` automatically
on parent save** (confirmed directly against `frappe/model/document.py`: `Document._save()`'s
`update_children()` only calls `d.db_update()` per row, never `run_method("validate")`). So
`project_custom_fields.validate_project` (Project's own `validate` doc_event, §1) explicitly
loops over `custom_egc_stakeholders` and calls `row.fetch_from_person()` on each — the same
workaround that section's WBS Node check already needed. **Any new child-table doctype in this
app that wants "always re-derive on save" behavior must do the same** — a doctype-controller
`validate()` alone will silently never fire outside whatever code path happens to duplicate its
logic manually (e.g. `project_profile.add_stakeholder`'s own pre-fill, which exists for the
unrelated reason that `party_name`'s `reqd` check runs before the row-level fetch would anyway).

### Organization resolution — ERPNext's own native Portal User mechanism, not a custom join

A person's organization is resolved via `directory.resolve_organization(user)`
(`egc_projects/egc_projects/directory.py`): checks whether `user` is a Portal User (the
`portal_users` child table, `options: "Portal User"`, that already exists on both core `Customer`
and `Supplier` — no fields added, no join table invented) of a `Customer`; if not, checks
`Supplier`; if neither, the person is **EGC-internal** (no organization at all — the correct
state for an EGC staff member holding an internal role, not an error case). This is why
`organization` on Stakeholder/`EGC Assignment` is a Dynamic Link, not a plain `Customer` Link —
the person-derived organization can genuinely be either a Customer or a Supplier.

A *directly*-picked organization (a PM typing one in without going through `person`) is always a
`Customer` — the Hub's own dialogs only offer a Customer-only picker for that manual path, and
`organization_type` field-defaults to `Customer` for exactly that reason (a **field-level**
default, not a controller one — `_validate_links()`, the Dynamic Link's own existence check,
runs before a row's `validate()` can set anything, so only a field-level default is early enough;
this bit both the `organization_type` field and the `party_name` `reqd` check for the same
underlying reason, and is worth internalizing as its own rule).

Every ERPNext organization in this app (client, consultant, main contractor, OEM, even EGC
itself when it needs a Directory identity, e.g. as a Submittal's Responsible Organization) is
plain `Customer` — **never split by ERPNext's own accounting Party Type** (Customer/Supplier/
Employee/Shareholder). Direct instruction: *"this has nothing to do with Accounting, this is a
very simple thing, it just tells me that this user is from this customer."* One new Custom
Field, `custom_organization_type` (Select, same options `Customer`'s old EGC-Organization
predecessor had — Client/Main Contractor/Consultant/Architect/OEM/Subcontractor/Specialty
Contractor/Supplier/Specialist Vendor/Other), preserves that org's own fixed global identity —
**distinct from, and never conflated with, this table's own `role`**, which is what that person
holds **on this one project** (rule: organization identity ≠ project role — EGC itself might be
a "Specialty Contractor" by global identity while acting as, say, a subcontractor to a Main
Contractor on one particular job; that's a Stakeholder Role, not a change to EGC's own
`custom_organization_type`).

**"Siemens / Philips / GE" become data, never schema**: role = `OEM`, `party_name` = whichever
manufacturer applies to that project. No manufacturer is ever a role, a Select option, or a
doctype (the equipment-item-level manufacturer master, `EGC Equipment Manufacturer`, §3, is a
separate, narrower concern — which piece of kit, not who represents the vendor on this project).

### Directory tab and Portal Access — `api/directory.py`

The Hub's Directory tab (`DirectoryTab.vue`) surfaces every Stakeholder row as an actionable
list — who's on the project, their role, whether they're internal or external, and whether they
can currently log into the Hub at all. "Portal Access" is nothing new: the same read-only
`EGC External Viewer` role + `User Permission`-scoped-to-one-Project pattern
`test_external_viewer.py` already proves out, just reachable from the Hub (`grant_portal_access`/
`revoke_portal_access`) instead of requiring a System Manager to wire it up by hand. Granting
access to a Stakeholder row with no `person` yet creates the `User` first (via a supplied email,
reusing an existing `User` of that address if one exists) and mirrors it straight onto that row's
`person` field — no separate identity record to mirror onto anymore, unlike the Level 0/Contact
eras of this same flow.

A client-side submittal **reviewer is not a separate access tier from a viewer**:
`record_step_response` (§7) authorizes purely by identity ("are you the assigned
`reviewer_user`"), not by doctype role permission — so `EGC External Viewer` already grants
everything an external reviewer needs to both watch a project and respond to a step assigned to
them. No separate "reviewer" role exists or is needed (a planned "EGC External Reviewer" role was
dropped mid-build for exactly this reason, once the actual authorization code was read rather
than assumed).

Add-Person dialogs across the Hub (Directory, Project Details, Activities, Submittals, Documents)
call a shared preview endpoint, `project_profile.get_person_info(person)`, wired as a `change`
callback on the Person field, so picking a person fills Party Name/Organization/Email/Phone live
in the dialog — the same resolution the record's own save-time mirroring does, just exposed for
a client-side preview instead of only surfacing after the record is actually created. The
Directory/Project-Details "Add Person" pickers additionally exclude anyone already on that
project's Directory (`get_query` filtering on the already-loaded stakeholder list) — Activity/
Submittal "Add Person" assignment dialogs deliberately do **not** apply that same exclusion,
since the same person legitimately holding two different roles on one Activity/Submittal is a
real, tested case (unlike the Directory, which is one row per person).

### Resolution source for the Submittal workflow engine (§7)

`egc_projects/egc_projects/project_profile.py` exposes (signatures unchanged since v1 — only the
internal `parenttype` filter moved from `"EGC Project Profile"` to `"Project"`, and the returned
value is now a `User` email directly rather than going through any intermediate identity record):
```python
def resolve_role_user(project: str, role_name: str) -> str | None: ...
def get_stakeholders(project: str) -> list[dict]: ...
```
A workflow template step naming `reviewer_role = "Consultant"` resolves, at instantiation time,
to that project's actual Stakeholder row with `role="Consultant"` and reads its `person` (or — if
the role's stakeholder has no `person` set, e.g. a pure external party with no Frappe login — the
step is recorded against `party_name` for display but cannot be a live in-app reviewer; the UI
must make this distinction obvious rather than silently failing to notify anyone).

### `EGC Assignment` — the generic multi-person/multi-organization relationship (§5/§7)

Same `person` (Link `User`)/`organization_type`+`organization` (Dynamic Link) shape as
Stakeholder, same Portal User-based resolution (`fetch_organization_from_person`, fill-if-blank
rather than always-overwrite — a caller may deliberately override the derived organization).
Standalone doctype (not a child table, unlike Stakeholder) because a person can be assigned
across many Activities/Submittals and one record can carry many assignees — a genuine
many-to-many. See §5/§6.

---

## 3. Healthcare / Equipment metadata

`EGC Modality` — small master (ARCH/MECH-style): `modality_name` (MRI, CT, X-Ray, Ultrasound,
Cath Lab, Linear Accelerator, Nuclear Medicine, Other), `enabled`.

`EGC Equipment Manufacturer` — small master: `manufacturer_name` (Siemens Healthineers,
Philips Healthcare, GE HealthCare, Canon Medical, Other), `enabled`. Free-text-extensible (a
user can still type any name via a Data field fallback if truly novel — do not hard-block on
the master list; the field on the child row itself stays a Link so the register stays clean,
but the master is trivially added to, unlike a hard-coded Select).

`EGC Project Equipment Item` — child table, now on `Project` itself
(`custom_egc_equipment_items`, `parenttype="Project"`): `facility` (Data), `department` (Data),
`modality` (Link `EGC Modality`), `wbs_node` (Link `EGC WBS Node`, optional — ties the equipment
to its physical WBS location, e.g. `MRI-01`), `equipment_manufacturer` (Link
`EGC Equipment Manufacturer`), `equipment_model` (Data), `oem_reference` (Data),
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
    # edit_profile is exactly frappe.has_permission("Project", "write", doc=project) — a UI
    # hint, not a bespoke gate.
  profile: {
    project_stage, sector, project_image, project_description,   # never null fields;
      # project_code no longer exists (§1) — dropped from this contract entirely, not just
      # left null
    key_stakeholders: [{role, role_label, party_name, organization, person}],
      # `person` is a User email directly (§2) — capped to a header-relevant subset (PM, Site
      # Manager, Client, Consultant, OEM); the FULL stakeholder/equipment list is fetched
      # separately via get_project_info()
  }   # ALWAYS a dict — the fields live directly on Project, so there is no separate row whose
      # absence needs representing. An untouched project's fields simply read as blank
      # (None / "" / []), same as any other fresh Project field.
}
```

One whitelisted read method (added to `api/hub.py`):
```python
get_project_info(project) -> full info dict incl. every field + full stakeholders[] +
  equipment_items[]   # gated on Project read permission only — read-only, no save counterpart.
```
Editing is `project_profile.py`'s own whitelisted functions (`save_project_profile`,
`add_stakeholder`/`remove_stakeholder`, `add_equipment_item`/`remove_equipment_item`), called
from the Hub's `ProjectInfoTab.vue` — §1's revision note above explains why this is no longer
"the native form only." The native `Project` form still works as a secondary path; nothing makes
it read-only.

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
- **Email is a genuinely additive second channel, added later** (`notify_email.py`, kept
  separate from `notifications.py` on purpose — that module's own docstring is explicit that
  Ball-in-Court delivery stays in-app-only via `assign_to`, never emailed). Two events reach an
  inbox: a review-requested email the moment `submittal_control._assign_step` creates the
  in-app assignment, and a one-time Directory welcome email the moment `grant_portal_access`
  (§2) first creates real Hub access for someone — guarded on current `User Permission`
  existence, not a separate "already welcomed" flag, so it fires again if access is properly
  revoked and later restored. Sent from the site's configured no-reply address, plain text, no
  `Email Template` doctype — deliberately simple per instruction.

### 7a. Expanded Submittal metadata — superseded by the Directory (§2)

> **Revision note:** `responsible_party`/`received_from` as originally specified below were
> plain free-text Data fields with no structured link, matching a "don't force a bad Customer/
> Supplier shoehorn" call that itself got superseded once §2's Directory model landed. Both
> fields **still exist** (as the controlled free-text fallback for a genuine one-off party), but
> each now has a companion Directory-linked field that — once set — always wins on save (Level 1,
> "Project Directory Must Be Used Everywhere"): `responsible_organization` (Link `Customer`,
> mirrors into `responsible_party` via `EGCSubmittal.fetch_from_directory()`) and
> `received_from_person` (Link `User`, mirrors into `received_from`, same mechanism). Same
> "always re-derive on save, not fill-once" discipline as Stakeholder's `person` (§2) — and the
> same standalone-doctype exception applies in the *other* direction here: `EGC Submittal` is
> not a child table, so its own `validate()` genuinely does fire on every save, unlike
> Stakeholder's child-row case.

Per the brief's "Expand Submittal Information": fields that manage a real construction
submission, not a bare identity. Added where they don't already exist and don't duplicate
something derivable — `related Activities` is not a field, it is the existing
`EGC Activity Link` relationship (§ v1 doc), and is not repeated here.

New on **`EGC Submittal`**: `responsible_party` (Data, controlled free-text fallback — see
revision note above), `responsible_organization` (Link `Customer`), `received_from` (Data,
same fallback), `received_from_person` (Link `User`), `submittal_manager` (Link `User`),
`ball_in_court` (Data, **read-only, engine-set** — mirrors `current_submission_label`'s pattern,
see §7's Ball in Court subsection), `specification_section` (Data, optional, reserved for future
spec-section cross-referencing — not used by any logic in v2).

New on **`EGC Project Document`** (the same Level 1 Directory-linking pass): `originator`
(Data, controlled free-text fallback) + `originator_person` (Link `User`, mirrors into
`originator` via `EGCProjectDocument.fetch_from_directory()`), same discipline.

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
| `egc_projects/notify_email.py` (new, Level 0) | Email notification channel (§7) — separate from `notifications.py`, kept that way deliberately |
| `api/directory.py` (new, Level 0) | Directory tab / Portal Access (§2) |
| `egc_projects/directory.py` (new, 2026-08-30) | `resolve_organization()` — the Portal User lookup every mirroring controller shares (§2) |
| `egc_projects/assignments.py` (new, Level 0) | `EGC Assignment`, the generic multi-person/multi-organization relationship (§2) |
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
