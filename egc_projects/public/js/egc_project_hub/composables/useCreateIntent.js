// Overview's "Quick Actions" (Level 1 §35: "+ Activity  + Submittal  + Document  + Drawing")
// must open the target tab's OWN "New …" dialog, not just switch to the tab and leave the user
// to find the button themselves — same one-shot-flag-before-switching-tabs pattern
// useOverdueIntent.js/useDrawingsIntent.js already established, since a create dialog is owned
// and only truly definable inside its own tab component (its own field list, its own project
// scoping), not something Quick Actions could reasonably open itself from the Hub shell.

import { reactive } from "vue";

export const createIntent = reactive({ activities: false, submittals: false, documents: false, drawings: false });

export function consumeCreateIntent(key) {
	const value = createIntent[key];
	createIntent[key] = false;
	return value;
}
