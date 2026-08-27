// Same one-shot click-through pattern as useOverdueIntent.js: the Overview tab's "Approved"
// drawings count must jump straight to Drawings pre-filtered to Approval Status = Approved, not
// just to an unfiltered register the user has to filter themselves.

import { reactive } from "vue";

export const drawingsIntent = reactive({ approvalStatus: null });

export function consumeDrawingsApprovalIntent() {
	const value = drawingsIntent.approvalStatus;
	drawingsIntent.approvalStatus = null;
	return value;
}
