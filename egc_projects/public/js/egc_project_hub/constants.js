// Small, deliberately shared file — most role-hint lists in this codebase are hardcoded locally
// per-component (a client-side-only UX hint, never the real permission boundary, which is always
// re-checked server-side), but FINANCIAL_ROLES has two simultaneous new consumers as of the
// portfolio dashboard (useHubRoute.js's redirect-suppression check and PortfolioDashboard.vue's
// own render gate) that must agree exactly, so it's worth not duplicating this one.
//
// Mirrors egc_projects/egc_projects/constants.py's FINANCIAL_ROLES verbatim. This is a UX hint
// only — the real gate is `_require_financial_access()` (api/hub.py), re-checked server-side on
// every financial call regardless of what this list says.
export const FINANCIAL_ROLES = ["EGC Project Manager", "Projects Manager", "Accounts User", "Accounts Manager", "System Manager"];

export function has_financial_access() {
	return (frappe.user_roles || []).some((role) => FINANCIAL_ROLES.includes(role));
}
