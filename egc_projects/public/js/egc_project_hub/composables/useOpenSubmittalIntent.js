// Same one-shot click-through pattern as useDrawingsIntent.js/useOverdueIntent.js: navigating
// from a Document's own page to a specific Submittal means switching to the Submittals tab AND
// telling it which record to open — the Hub's route only carries project/tab, not a record
// within a tab, so a one-shot intent is how a caller in one tab hands a target record to
// whichever tab mounts next, without a route schema change.

import { reactive } from "vue";

export const openSubmittalIntent = reactive({ submittal: null });

export function consumeOpenSubmittalIntent() {
	const value = openSubmittalIntent.submittal;
	openSubmittalIntent.submittal = null;
	return value;
}
