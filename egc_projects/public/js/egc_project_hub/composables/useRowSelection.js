// Row-checkbox selection state for a Hub register table — mirrors Frappe's own List View
// convention (a checkbox per row, a header checkbox that selects everything currently visible,
// an indeterminate state when some-but-not-all rows are checked). Deliberately generic: every
// tab that has a flat table of rows (ActivitiesTab, SubmittalsTab, DocumentsTab; WbsTab's tree
// wires it differently, see WbsTab.vue) uses this same composable instead of hand-rolling
// selection state four times over.

import { ref, computed, watch } from "vue";

/**
 * @param {import("vue").Ref<Array>} rowsRef - the currently-visible/filtered rows
 * @param {(row: object) => string} [keyFn] - defaults to row.name
 */
export function useRowSelection(rowsRef, keyFn = (row) => row.name) {
	const selected = ref(new Set());

	// A filter change can leave stale keys selected for rows no longer visible — Frappe's own
	// List View clears selection on any filter/search change rather than let it go stale.
	watch(rowsRef, () => {
		if (selected.value.size) selected.value = new Set();
	});

	const visible_keys = computed(() => rowsRef.value.map(keyFn));
	const selected_count = computed(() => selected.value.size);
	const all_selected = computed(
		() => visible_keys.value.length > 0 && visible_keys.value.every((k) => selected.value.has(k))
	);
	const some_selected = computed(() => selected.value.size > 0 && !all_selected.value);

	function is_selected(row) {
		return selected.value.has(keyFn(row));
	}

	function toggle(row) {
		const key = keyFn(row);
		const next = new Set(selected.value);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		selected.value = next;
	}

	function toggle_all() {
		selected.value = all_selected.value ? new Set() : new Set(visible_keys.value);
	}

	function clear() {
		selected.value = new Set();
	}

	return {
		selected,
		selected_count,
		all_selected,
		some_selected,
		is_selected,
		toggle,
		toggle_all,
		clear,
	};
}
