// Overdue counts on the Overview tab must click through to the filtered list (spec §5). Overdue
// is derived server-side, not a stored field the Activities/Submittals filters accept, so the
// Overview tab sets this one-shot flag before switching tabs and the target tab consumes it.

import { reactive } from "vue";

export const overdueIntent = reactive({ activities: false, submittals: false });

export function consumeOverdueIntent(key) {
	const value = overdueIntent[key];
	overdueIntent[key] = false;
	return value;
}
