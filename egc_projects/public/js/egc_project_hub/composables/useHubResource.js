// Small loading/error/data wrapper shared by every tab so each one doesn't reimplement the
// same three states (spec: every tab needs a real loading state, empty state and error state).

import { ref } from "vue";

export function useHubResource(loader) {
	const data = ref(null);
	const loading = ref(false);
	const error = ref("");

	async function reload(...args) {
		loading.value = true;
		error.value = "";
		try {
			data.value = await loader(...args);
		} catch (e) {
			error.value = e.message || String(e);
		} finally {
			loading.value = false;
		}
	}

	return { data, loading, error, reload };
}
