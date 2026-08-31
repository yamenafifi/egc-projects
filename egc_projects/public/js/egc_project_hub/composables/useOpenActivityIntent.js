// The Activities-side counterpart of useOpenDocumentIntent.js/useOpenSubmittalIntent.js — a
// Document/Submittal's own page (or the Overview tab's My Tasks/Recent Activity feeds) linking to
// an Activity needs to open that Activity's own full-page detail in the Activities tab, not the
// raw native form. Same one-shot pattern as useDrawingsIntent.js.

import { reactive } from "vue";

export const openActivityIntent = reactive({ activity: null });

export function consumeOpenActivityIntent() {
	const value = openActivityIntent.activity;
	openActivityIntent.activity = null;
	return value;
}
