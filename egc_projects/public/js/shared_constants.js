// Small, genuinely static option lists shared between the native-Desk client script
// (egc_activity_links.js) and the Project Hub's Vue components (ActivityDetail.vue,
// ActivityFullPage.vue, ActivityLinkedRecords.vue) — all four used to hand-type their own
// identical copy of these two arrays instead of sharing one. Mirrors the backend's own
// `constants.py` values (`DEPENDENCY_TYPES`, `LINK_PURPOSES`) — kept here rather than fetched
// from the server because these never change at runtime and a Select field's options must be
// available synchronously when a dialog is built.

export const DEPENDENCY_TYPES = ["Finish-to-Start", "Start-to-Start", "Finish-to-Finish", "Start-to-Finish"];

export const LINK_PURPOSES = ["Reference", "Requirement"];
