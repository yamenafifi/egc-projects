// Same one-shot click-through pattern as useOverdueIntent.js: the Overview tab's "Approved"
// drawings count must jump straight to Documents, with "Drawings only" on and Approval Status =
// Approved already set, not just to an unfiltered register the user has to filter themselves.
// (Drawings used to be its own tab; folded into Documents' own "Drawings only" toggle — see
// DocumentsTab.vue.)

import { reactive } from "vue";

export const drawingsIntent = reactive({ approvalStatus: null });

export function consumeDrawingsApprovalIntent() {
	const value = drawingsIntent.approvalStatus;
	drawingsIntent.approvalStatus = null;
	return value;
}
