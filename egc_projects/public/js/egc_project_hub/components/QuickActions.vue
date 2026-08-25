<!-- Header-level "Quick Actions" affordance (ARCHITECTURE_V2.md §0 finding 3 — Overview had no
quick actions). The actual creation UI lives in each target tab's own package, not here, and
none of those tabs expose an in-place creation dialog yet — so for this wave every action just
navigates to its tab. TODO: once Activities/Submittals/Documents/Drawings expose a "New …"
dialog, wire these straight into it instead of a tab switch.

Click-outside is done via a real document listener (checked against a template ref), not a
focusout/blur handler — a blur fires before the menu item's own click event completes, which
would unmount the item (v-if="open") out from under that in-flight click. That is the same class
of unmount race documented in ProjectLinkControl.vue; this sidesteps it instead of reintroducing
it. -->
<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useHubRoute } from "../composables/useHubRoute";

const { setTab } = useHubRoute();
const open = ref(false);
const container = ref(null);

const ACTIONS = [
	{ tab: "activities", label: __("New Activity") },
	{ tab: "submittals", label: __("New Submittal") },
	{ tab: "documents", label: __("New Document") },
	{ tab: "drawings", label: __("New Drawing") },
];

function toggle() {
	open.value = !open.value;
}

function trigger(tab) {
	open.value = false;
	setTab(tab);
}

function on_document_click(e) {
	if (open.value && container.value && !container.value.contains(e.target)) open.value = false;
}

onMounted(() => document.addEventListener("click", on_document_click));
onBeforeUnmount(() => document.removeEventListener("click", on_document_click));
</script>

<template>
	<div ref="container" class="hub-quick-actions">
		<button type="button" class="btn btn-sm btn-default" :aria-expanded="open" @click="toggle">
			{{ __("Quick Actions") }}
			<span class="hub-quick-actions__caret">▾</span>
		</button>
		<div v-if="open" class="hub-quick-actions__menu" role="menu">
			<button
				v-for="action in ACTIONS"
				:key="action.tab"
				type="button"
				role="menuitem"
				class="hub-quick-actions__item"
				@click="trigger(action.tab)"
			>
				{{ action.label }}
			</button>
		</div>
	</div>
</template>

<style scoped>
.hub-quick-actions {
	position: relative;
	flex: 0 0 auto;
}

.hub-quick-actions__caret {
	font-size: 10px;
	margin-left: 2px;
}

.hub-quick-actions__menu {
	position: absolute;
	top: calc(100% + 4px);
	right: 0;
	z-index: 10;
	min-width: 170px;
	display: flex;
	flex-direction: column;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	background: var(--fg-color);
	box-shadow: var(--shadow-lg, 0 4px 16px rgba(0, 0, 0, 0.12));
	padding: 4px;
}

.hub-quick-actions__item {
	appearance: none;
	background: none;
	border: none;
	text-align: left;
	padding: 7px 10px;
	font-size: var(--text-sm);
	color: var(--text-color);
	border-radius: var(--border-radius);
	cursor: pointer;
}

.hub-quick-actions__item:hover {
	background: var(--control-bg);
}
</style>
