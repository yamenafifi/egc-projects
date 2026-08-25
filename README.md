## EGC Projects

Construction project management for EGC, built on Frappe v16 and ERPNext v16.

EGC Projects extends the standard ERPNext `Project` — it does not replace it — with the
document-control and work-breakdown semantics a specialty healthcare contractor needs:

- **WBS** — a project-scoped hierarchy of arbitrary depth and shape, independent of discipline.
- **Activities** — a separate execution hierarchy using one self-referencing DocType at every
  level, classified by WBS node and discipline.
- **Controlled Documents** — a document identity with an accumulating, immutable revision
  history. Issuing a revision supersedes the previous one; it never overwrites it.
- **Drawing Register** — drawings presented as a construction register, with the current
  revision and its true approval state.
- **Submittals** — a persistent submittal identity whose submission/review cycles are kept as
  history, so a *Revise & Resubmit* creates a new cycle instead of erasing the old one.
- **Project Hub** — one project-centric workspace covering Overview, WBS, Activities,
  Submittals, Drawings and Financials without losing project context.
- **Financials** — read live from the ERPNext Project. EGC Projects keeps no second ledger.

See `docs/ARCHITECTURE.md` for the design and `CLAUDE.md` for contributor guidance.

#### Installation

```bash
bench get-app https://github.com/yamenafifi/egc-projects.git
bench --site <site> install-app egc_projects
```

#### License

MIT
