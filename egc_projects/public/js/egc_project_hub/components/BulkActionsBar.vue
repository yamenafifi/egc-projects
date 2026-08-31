<!-- Appears in place of the toolbar once at least one row is checked — matches the Frappe List
View's own "N selected · Actions ▾" bar, scoped down to what this Hub actually needs: Export the
selection, and Delete it (write-gated, same as every other destructive action in this app). -->
<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";

const props = defineProps({
	selectedCount: { type: Number, required: true },
	canDelete: { type: Boolean, default: false },
});
const emit = defineEmits(["export", "delete", "clear"]);

const menu_open = ref(false);
const menu_container = ref(null);

function on_document_click(e) {
	if (menu_open.value && menu_container.value && !menu_container.value.contains(e.target)) {
		menu_open.value = false;
	}
}
onMounted(() => document.addEventListener("click", on_document_click));
onBeforeUnmount(() => document.removeEventListener("click", on_document_click));

function run(action) {
	menu_open.value = false;
	action();
}
</script>

<template>
	<div class="hub-bulk-bar">
		<button type="button" class="hub-bulk-bar__clear" :title="__('Clear selection')" @click="emit('clear')">
			✕
		</button>
		<span class="hub-bulk-bar__count">{{ __("{0} selected", [selectedCount]) }}</span>
		<span ref="menu_container" class="hub-bulk-bar__menu">
			<button type="button" class="btn btn-xs btn-default" @click.stop="menu_open = !menu_open">
				{{ __("Actions") }} ▾
			</button>
			<div v-if="menu_open" class="hub-bulk-bar__dropdown" role="menu">
				<button type="button" role="menuitem" @click.stop="run(() => emit('export'))">
					{{ __("Export Selected") }}
				</button>
				<button
					v-if="canDelete"
					type="button"
					role="menuitem"
					class="hub-bulk-bar__danger"
					@click.stop="run(() => emit('delete'))"
				>
					{{ __("Delete Selected") }}
				</button>
			</div>
		</span>
	</div>
</template>

<style scoped>
.hub-bulk-bar {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 7px 10px;
	border-bottom: 1px solid var(--border-color);
	background: var(--control-bg);
	font-size: var(--text-sm);
}

.hub-bulk-bar__clear {
	appearance: none;
	border: none;
	background: none;
	color: var(--text-muted);
	cursor: pointer;
	font-size: var(--text-sm);
	line-height: 1;
	padding: 2px;
}

.hub-bulk-bar__clear:hover {
	color: var(--text-color);
}

.hub-bulk-bar__count {
	font-weight: 500;
	color: var(--text-color);
}

.hub-bulk-bar__menu {
	position: relative;
	margin-left: auto;
}

.hub-bulk-bar__dropdown {
	position: absolute;
	top: calc(100% + 4px);
	right: 0;
	z-index: 10;
	min-width: 150px;
	display: flex;
	flex-direction: column;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	background: var(--fg-color);
	box-shadow: var(--shadow-lg, 0 4px 16px rgba(0, 0, 0, 0.12));
	padding: 4px;
}

.hub-bulk-bar__dropdown button {
	appearance: none;
	background: none;
	border: none;
	text-align: left;
	padding: 6px 10px;
	font-size: var(--text-sm);
	color: var(--text-color);
	border-radius: var(--border-radius);
	cursor: pointer;
}

.hub-bulk-bar__dropdown button:hover {
	background: var(--control-bg);
}

.hub-bulk-bar__danger {
	color: var(--red-500, var(--text-on-red));
}
</style>
