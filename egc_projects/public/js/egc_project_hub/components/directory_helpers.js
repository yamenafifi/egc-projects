// Direct user instruction: "the originator or whatever should be from the project directory
// people STRICTLY" — every Link-to-User field in a creation form (Originator, Received From,
// Submittal Manager, ...) must offer ONLY people already on this project's own Directory
// (`custom_egc_stakeholders`), never any User in the whole site, and the controlled free-text
// fallback fields these used to pair with are dropped from creation forms entirely (the
// underlying doctype fields still exist for old data — this only tightens what the FORMS offer
// going forward, per the same instruction: "clean up this mess").
//
// One shared helper rather than every dialog re-fetching/re-filtering the Directory itself.

import { get_directory } from "./directory_api";

/**
 * @param {string} project
 * @returns {Promise<string[]>} every distinct `person` (User email) already on this project's
 *   Directory — empty when nobody has been added yet (the picker will then correctly show no
 *   matches, per "STRICTLY": add the person to the Directory first, don't type them in here).
 */
export async function get_directory_person_emails(project) {
	const rows = await get_directory(project).catch(() => []);
	return [...new Set(rows.map((r) => r.person).filter(Boolean))];
}

/**
 * @param {string} project
 * @returns {Promise<string[]>} every distinct `organization` (Customer name) already on this
 *   project's Directory.
 */
export async function get_directory_organization_names(project) {
	const rows = await get_directory(project).catch(() => []);
	return [...new Set(rows.map((r) => r.organization).filter(Boolean))];
}

/**
 * A `get_query` for a Link(User) field, restricted to `emails`. Frappe's Link `get_query` still
 * runs its own text search against the User doctype — this only narrows the candidate set to the
 * given names, exactly like the Directory's own "Add Person" pickers already narrow by exclusion
 * (this is the inclusion mirror of that same pattern, see api/directory.py's DirectoryTab.vue
 * usage).
 */
export function person_link_filter(emails) {
	return () => ({ filters: { name: ["in", emails.length ? emails : ["__none__"]] } });
}

/** Same shape, for a Link(Customer) field restricted to this project's Directory organizations. */
export function organization_link_filter(names) {
	return () => ({ filters: { name: ["in", names.length ? names : ["__none__"]] } });
}
