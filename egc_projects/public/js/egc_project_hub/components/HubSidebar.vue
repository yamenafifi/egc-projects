<!-- The Hub's own persistent left navigation shell — a Procore-style tool switcher, not the
horizontal tab bar it replaces (TabNav.vue, removed). This is the piece that makes the Hub read
as its own independent application inside Desk rather than a themed DocType view: a fixed icon
rail owns "which tool," the content area owns "that tool's content," full height, no nesting
inside a Desk page-head/breadcrumb bar (see egc_project_hub.js's `page_head.hide()`). -->
<script setup>
import { ref } from "vue";
import ProjectLinkControl from "./ProjectLinkControl.vue";

const props = defineProps({
	project: { type: String, required: true },
	projectName: { type: String, default: "" },
	tabs: { type: Array, required: true },
	active: { type: String, required: true },
	// Below the ~900px breakpoint (see the scoped style block) the sidebar becomes an
	// off-canvas drawer instead of a static column — `open` controls whether it's slid in.
	// Ignored above the breakpoint, where the sidebar is always visible.
	open: { type: Boolean, default: false },
});
const emit = defineEmits(["select", "switch-project", "close"]);

function on_select(key) {
	emit("select", key);
	emit("close");
}

const switching = ref(false);

function on_switch(value) {
	// Same unmount-race fix as HubHeader.vue's own on_switch: ProjectLinkControl's underlying
	// awesomplete keeps running async validation after calling this handler, so let that finish
	// on the next macrotask before this component tears the control's DOM down.
	setTimeout(() => {
		switching.value = false;
	}, 0);
	if (value && value !== props.project) {
		emit("switch-project", value);
		emit("close");
	}
}

function open_workspace() {
	frappe.set_route("egc-projects");
}

// One small stroke-based icon per tool, hand-authored rather than borrowed from Frappe's own
// icon sprite (frappe.utils.icon) — a distinct icon set is part of what should make this shell
// feel like its own product rather than Desk-flavoured chrome.
const ICONS = {
	overview:
		'<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
	wbs: '<circle cx="5" cy="5" r="2.2"/><circle cx="19" cy="5" r="2.2"/><circle cx="19" cy="19" r="2.2"/><circle cx="12" cy="19" r="2.2"/><path d="M5 7.2V17a2 2 0 0 0 2 2h3M19 7.2v9.6"/>',
	activities:
		'<path d="M9 4h10a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H9"/><path d="M4 4h2v3H4zM4 10.5h2v3H4zM4 17h2v3H4z"/><path d="M11 8h6M11 12h6M11 16h4"/>',
	submittals:
		'<path d="M21 3 3 10.5l7 2.5m11-10L14 21l-4-8m11-10L10 13"/>',
	documents:
		'<path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1Z"/><path d="M14 3v4h4"/><path d="M9 12h6M9 15.5h6M9 8.5h2"/>',
	drawings:
		'<path d="m4 20 6.5-6.5"/><path d="M13.5 4.5 19.5 10.5 10.5 19.5 4.5 19.5 4.5 13.5 13.5 4.5Z"/><path d="M11.5 6.5 17.5 12.5"/>',
	financials:
		'<path d="M12 2v20"/><path d="M17 6.5c0-1.7-2.2-3-5-3s-5 1.2-5 3 2.2 2.5 5 3 5 1.3 5 3-2.2 3-5 3-5-1.3-5-3"/>',
	"project-info":
		'<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.5" r="0.25" fill="currentColor" stroke="none"/>',
};
</script>

<template>
	<div v-if="open" class="egc-sidebar__backdrop" @click="$emit('close')"></div>
	<aside class="egc-sidebar" :class="{ 'egc-sidebar--open': open }">
		<button type="button" class="egc-sidebar__brand" @click="open_workspace">
			<span class="egc-sidebar__brand-mark">EGC</span>
			<span class="egc-sidebar__brand-name">{{ __("Projects") }}</span>
		</button>

		<div class="egc-sidebar__project">
			<template v-if="!switching">
				<div class="egc-sidebar__project-code">{{ project }}</div>
				<div class="egc-sidebar__project-name">{{ projectName }}</div>
				<button type="button" class="egc-sidebar__project-switch" @click="switching = true">
					{{ __("Switch Project") }}
				</button>
			</template>
			<ProjectLinkControl
				v-else
				:model-value="project"
				:placeholder="__('Search projects…')"
				@update:model-value="on_switch"
			/>
		</div>

		<nav class="egc-sidebar__nav">
			<button
				v-for="tab in tabs"
				:key="tab.key"
				type="button"
				class="egc-sidebar__item"
				:class="{ 'egc-sidebar__item--active': tab.key === active }"
				@click="on_select(tab.key)"
			>
				<svg
					class="egc-sidebar__icon"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.6"
					stroke-linecap="round"
					stroke-linejoin="round"
					v-html="ICONS[tab.key]"
				></svg>
				<span>{{ tab.label }}</span>
			</button>
		</nav>
	</aside>
</template>

<style scoped>
.egc-sidebar {
	width: 232px;
	flex: 0 0 232px;
	height: 100%;
	display: flex;
	flex-direction: column;
	background: var(--egc-sidebar-bg);
	border-right: 1px solid var(--egc-sidebar-border);
	overflow-y: auto;
}

.egc-sidebar__brand {
	appearance: none;
	border: none;
	background: none;
	cursor: pointer;
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 16px 18px;
	text-align: left;
}

.egc-sidebar__brand-mark {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	width: 26px;
	height: 26px;
	border-radius: 7px;
	background: var(--egc-accent);
	color: var(--egc-accent-contrast);
	font-size: 11px;
	font-weight: 700;
	letter-spacing: 0.02em;
}

.egc-sidebar__brand-name {
	font-size: var(--text-md);
	font-weight: 600;
	color: var(--egc-sidebar-text);
}

.egc-sidebar__project {
	padding: 4px 18px 16px;
	border-bottom: 1px solid var(--egc-sidebar-border);
	margin-bottom: 10px;
}

.egc-sidebar__project-code {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--egc-sidebar-text-muted);
	text-transform: uppercase;
	letter-spacing: 0.04em;
}

.egc-sidebar__project-name {
	font-size: var(--text-sm);
	color: var(--egc-sidebar-text);
	margin-top: 2px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.egc-sidebar__project-switch {
	appearance: none;
	border: none;
	background: none;
	cursor: pointer;
	padding: 0;
	margin-top: 8px;
	font-size: var(--text-xs);
	color: var(--egc-accent);
}

.egc-sidebar__project-switch:hover {
	text-decoration: underline;
}

.egc-sidebar__nav {
	display: flex;
	flex-direction: column;
	gap: 2px;
	padding: 0 10px;
}

.egc-sidebar__item {
	appearance: none;
	border: none;
	background: none;
	cursor: pointer;
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 9px 10px;
	border-radius: var(--border-radius);
	font-size: var(--text-sm);
	font-weight: 500;
	color: var(--egc-sidebar-text-muted);
	text-align: left;
	border-left: 3px solid transparent;
}

.egc-sidebar__item:hover {
	background: var(--egc-sidebar-hover);
	color: var(--egc-sidebar-text);
}

.egc-sidebar__item--active {
	background: var(--egc-sidebar-active-bg);
	color: var(--egc-sidebar-text);
	border-left-color: var(--egc-accent);
}

.egc-sidebar__icon {
	width: 18px;
	height: 18px;
	flex: 0 0 auto;
}

/* Below ~900px (a tablet/phone width, not just phones) the fixed rail no longer fits alongside
   readable content — it becomes an off-canvas drawer instead, matching how Procore's own
   responsive web view collapses its tool switcher. */
@media (max-width: 900px) {
	.egc-sidebar {
		position: fixed;
		z-index: 600;
		left: 0;
		top: 0;
		box-shadow: var(--shadow-lg, 2px 0 12px rgba(0, 0, 0, 0.15));
		transform: translateX(-100%);
		transition: transform 0.18s ease;
	}

	.egc-sidebar--open {
		transform: translateX(0);
	}

	.egc-sidebar__backdrop {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.35);
		z-index: 500;
	}
}
</style>
