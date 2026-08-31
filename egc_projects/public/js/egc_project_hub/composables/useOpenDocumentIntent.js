// The Documents-side mirror of useOpenSubmittalIntent.js — a Submittal's own page linking to one
// of its tracked documents needs to open that document's detail drawer in the Documents tab, not
// the raw native form. Same one-shot pattern as useDrawingsIntent.js.

import { reactive } from "vue";

export const openDocumentIntent = reactive({ document: null });

export function consumeOpenDocumentIntent() {
	const value = openDocumentIntent.document;
	openDocumentIntent.document = null;
	return value;
}
