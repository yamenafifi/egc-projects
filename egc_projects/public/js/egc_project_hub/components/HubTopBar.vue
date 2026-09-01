<!-- The Hub's persistent top bar — Procore's own layout (logo/home → company+project switcher →
     Toolbox tool-switcher dropdown, left to right in one bar), not a left icon rail (HubSidebar.vue,
     removed). Styling stays ERPNext-native (Frappe's own CSS variables, no black/orange Procore
     skin) — it's the STRUCTURE being matched, per an explicit annotated Procore reference, not the
     brand. Desk's own navbar is hidden for this page (egc_project_hub.js), so notifications/theme/
     profile are reproduced here using Frappe's own actual widgets (frappe.ui.Notifications,
     frappe.ui.ThemeSwitcher, frappe.avatar + frappe.ui.create_menu) instead of being reinvented —
     project status/progress used to live here too but has moved down into HubHeader.vue. -->
<script setup>
import { ref } from "vue";
import ProjectLinkControl from "./ProjectLinkControl.vue";

const props = defineProps({
	project: { type: String, required: true },
	projectName: { type: String, default: "" },
	tabs: { type: Array, required: true },
	active: { type: String, required: true },
});
const emit = defineEmits(["select", "switch-project"]);

const logo_broken = ref(false);

function on_select(key) {
	emit("select", key);
	tool_menu_open.value = false;
}

const switching = ref(false);

function on_switch(value) {
	// Same unmount-race fix as ProjectLinkControl's other callers: awesomplete keeps running
	// async validation after this handler returns, so let that finish before this component
	// tears the control's DOM down.
	setTimeout(() => {
		switching.value = false;
	}, 0);
	if (value && value !== props.project) emit("switch-project", value);
}

function open_workspace() {
	frappe.set_route("egc-projects");
}

const tool_menu_open = ref(false);
const tool_container = ref(null);

function toggle_tool_menu() {
	tool_menu_open.value = !tool_menu_open.value;
}

function on_document_click(e) {
	if (tool_menu_open.value && tool_container.value && !tool_container.value.contains(e.target)) {
		tool_menu_open.value = false;
	}
}

import { onBeforeUnmount, onMounted, computed } from "vue";

// -- notifications / theme / profile — Frappe's own widgets, reused as-is since Desk's native
// navbar is hidden behind this page. Mirrors frappe/desk/page/desktop/desktop.js's own
// setup_notifications()/setup_avatar(), trimmed to what makes sense embedded in a project page. --
const notif_wrapper = ref(null);
const avatar_wrapper = ref(null);
const is_dark = ref(frappe.ui.get_current_theme() === "dark");
let theme_observer = null;

function open_theme_switcher() {
	new frappe.ui.ThemeSwitcher().show();
}

onMounted(() => {
	document.addEventListener("click", on_document_click);

	new frappe.ui.Notifications({ wrapper: $(notif_wrapper.value), full_height: false });

	$(avatar_wrapper.value).html(frappe.avatar(frappe.session.user, "avatar-medium"));
	frappe.ui.create_menu({
		parent: $(avatar_wrapper.value),
		menu_items: [
			{
				icon: "edit",
				label: __("Edit Profile"),
				onClick: () => frappe.set_route("Form", "User", frappe.session.user),
			},
			{ icon: "log-out", label: __("Logout"), onClick: () => frappe.app.logout() },
		],
		open_on_left: !frappe.utils.is_rtl(),
	});

	// frappe.ui.set_theme flips the `data-theme` attribute with no accompanying JS event, so the
	// sun/moon icon has to watch the DOM directly to stay in sync with the ThemeSwitcher dialog.
	theme_observer = new MutationObserver(() => {
		is_dark.value = frappe.ui.get_current_theme() === "dark";
	});
	theme_observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
});

onBeforeUnmount(() => {
	document.removeEventListener("click", on_document_click);
	theme_observer && theme_observer.disconnect();
});

const active_tab = computed(() => props.tabs.find((t) => t.key === props.active));

// One small stroke-based icon per tool, hand-authored rather than borrowed from Frappe's own
// icon sprite — a distinct icon set is part of what makes this feel like its own product.
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
	directory:
		'<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17" cy="8" r="2.5"/><path d="M15.5 14.3c2.9.4 5 2.8 5 5.7"/>',
	financials:
		'<line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
	"project-info":
		'<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><circle cx="12" cy="7.5" r="0.25" fill="currentColor" stroke="none"/>',
};
</script>

<template>
	<div class="egc-topbar2">
		<button type="button" class="egc-topbar2__brand" :title="__('EGC Projects')" @click="open_workspace">
			<img
				v-if="!logo_broken"
				src="/files/qr_logo.png"
				class="egc-topbar2__logo"
				alt="EGC"
				@error="logo_broken = true"
			/>
			<span v-else class="egc-topbar2__logo-fallback">{{ __("EGC Projects") }}</span>
		</button>

		<div class="egc-topbar2__divider" />

		<div class="egc-topbar2__switcher">
			<template v-if="!switching">
				<button type="button" class="egc-topbar2__project" @click="switching = true">
					<span class="egc-topbar2__project-code">{{ project }}</span>
					<span class="egc-topbar2__project-name">{{ projectName || "—" }}</span>
				</button>
			</template>
			<ProjectLinkControl
				v-else
				:model-value="project"
				:placeholder="__('Search projects…')"
				@update:model-value="on_switch"
			/>
		</div>

		<div class="egc-topbar2__divider" />

		<div ref="tool_container" class="egc-topbar2__toolbox">
			<button type="button" class="egc-topbar2__toolbox-btn" :aria-expanded="tool_menu_open" @click="toggle_tool_menu">
				<svg
					v-if="active_tab"
					class="egc-topbar2__toolbox-icon"
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.8"
					stroke-linecap="round"
					stroke-linejoin="round"
					v-html="ICONS[active_tab.key]"
				></svg>
				<span class="egc-topbar2__toolbox-label">
					<span class="egc-topbar2__toolbox-eyebrow">{{ __("Toolbox") }}</span>
					<span class="egc-topbar2__toolbox-current">{{ active_tab ? active_tab.label : "" }}</span>
				</span>
				<span class="egc-topbar2__caret">▾</span>
			</button>

			<div v-if="tool_menu_open" class="egc-topbar2__menu" role="menu">
				<button
					v-for="tab in tabs"
					:key="tab.key"
					type="button"
					role="menuitem"
					class="egc-topbar2__menu-item"
					:class="{ 'egc-topbar2__menu-item--active': tab.key === active }"
					@click="on_select(tab.key)"
				>
					<svg
						class="egc-topbar2__menu-icon"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.8"
						stroke-linecap="round"
						stroke-linejoin="round"
						v-html="ICONS[tab.key]"
					></svg>
					{{ tab.label }}
				</button>
			</div>
		</div>

		<div class="egc-topbar2__spacer" />

		<div class="egc-topbar2__utility">
			<div ref="notif_wrapper" class="egc-topbar2__notif">
				<div class="dropdown dropdown-notifications">
					<button
						type="button"
						class="btn-reset egc-topbar2__icon-btn"
						data-toggle="dropdown"
						aria-haspopup="true"
						:aria-label="__('Notifications')"
						v-html="frappe.utils.icon('bell', 'md')"
					></button>
					<div style="top: unset" class="dropdown-menu dropdown-menu-right notifications-list" role="menu">
						<div class="notification-list-header">
							<div class="header-items"></div>
							<div class="header-actions"></div>
						</div>
						<div class="notification-list-body">
							<div class="panel-notifications"></div>
							<div class="panel-events"></div>
							<div class="panel-changelog-feed"></div>
						</div>
					</div>
				</div>
			</div>

			<button
				type="button"
				class="btn-reset egc-topbar2__icon-btn"
				:title="__('Toggle Theme')"
				:aria-label="__('Toggle Theme')"
				@click="open_theme_switcher"
				v-html="frappe.utils.icon(is_dark ? 'sun' : 'moon', 'md')"
			></button>

			<div ref="avatar_wrapper" class="egc-topbar2__avatar"></div>
		</div>
	</div>
</template>

<style scoped>
.egc-topbar2 {
	display: flex;
	align-items: center;
	gap: 4px;
	padding: 6px 16px;
	background: var(--fg-color);
	border-bottom: 1px solid var(--border-color);
	flex: 0 0 auto;
	flex-wrap: wrap;
}

.egc-topbar2__brand {
	appearance: none;
	border: none;
	background: none;
	cursor: pointer;
	display: flex;
	align-items: center;
	padding: 4px;
	flex: 0 0 auto;
}

.egc-topbar2__logo {
	height: 30px;
	width: auto;
	max-width: 120px;
	object-fit: contain;
}

.egc-topbar2__logo-fallback {
	font-size: var(--text-md);
	font-weight: 600;
	color: var(--text-color);
	padding: 0 6px;
}

.egc-topbar2__divider {
	width: 1px;
	align-self: stretch;
	margin: 6px 4px;
	background: var(--border-color);
	flex: 0 0 auto;
}

.egc-topbar2__switcher {
	flex: 0 1 auto;
	min-width: 0;
}

.egc-topbar2__project {
	appearance: none;
	border: none;
	background: none;
	cursor: pointer;
	display: flex;
	flex-direction: column;
	align-items: flex-start;
	padding: 6px 10px;
	border-radius: var(--border-radius);
	max-width: 260px;
}

.egc-topbar2__project:hover {
	background: var(--control-bg);
}

.egc-topbar2__project-code {
	font-size: 10px;
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.04em;
}

.egc-topbar2__project-name {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	max-width: 240px;
}

.egc-topbar2__toolbox {
	position: relative;
	flex: 0 0 auto;
}

.egc-topbar2__toolbox-btn {
	appearance: none;
	border: none;
	background: none;
	cursor: pointer;
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 5px 10px;
	border-radius: var(--border-radius);
}

.egc-topbar2__toolbox-btn:hover {
	background: var(--control-bg);
}

.egc-topbar2__toolbox-icon {
	width: 18px;
	height: 18px;
	color: var(--text-color);
	flex: 0 0 auto;
}

.egc-topbar2__toolbox-label {
	display: flex;
	flex-direction: column;
	align-items: flex-start;
}

.egc-topbar2__toolbox-eyebrow {
	font-size: 10px;
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.04em;
}

.egc-topbar2__toolbox-current {
	font-size: var(--text-sm);
	font-weight: 600;
	color: var(--text-color);
}

.egc-topbar2__caret {
	font-size: 10px;
	color: var(--text-muted);
	margin-left: 2px;
}

.egc-topbar2__menu {
	position: absolute;
	top: calc(100% + 4px);
	left: 0;
	z-index: 600;
	min-width: 210px;
	display: flex;
	flex-direction: column;
	gap: 2px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius-lg);
	background: var(--fg-color);
	box-shadow: var(--shadow-lg, 0 4px 16px rgba(0, 0, 0, 0.12));
	padding: 6px;
}

.egc-topbar2__menu-item {
	appearance: none;
	border: none;
	background: none;
	cursor: pointer;
	display: flex;
	align-items: center;
	gap: 10px;
	text-align: left;
	padding: 8px 10px;
	font-size: var(--text-sm);
	font-weight: 500;
	color: var(--text-color);
	border-radius: var(--border-radius);
}

.egc-topbar2__menu-item:hover {
	background: var(--control-bg);
}

.egc-topbar2__menu-item--active {
	background: var(--bg-light-blue, var(--control-bg));
	color: var(--text-on-light-blue, var(--text-color));
}

.egc-topbar2__menu-icon {
	width: 17px;
	height: 17px;
	flex: 0 0 auto;
}

.egc-topbar2__spacer {
	flex: 1 1 auto;
}

.egc-topbar2__utility {
	display: flex;
	align-items: center;
	gap: 4px;
	flex: 0 0 auto;
}

.egc-topbar2__icon-btn {
	display: flex;
	align-items: center;
	justify-content: center;
	width: 32px;
	height: 32px;
	padding: 0;
	border: none;
	border-radius: var(--border-radius);
	background: none;
	color: var(--text-muted);
	cursor: pointer;
}

.egc-topbar2__icon-btn:hover {
	background: var(--control-bg);
	color: var(--text-color);
}

.egc-topbar2__icon-btn :deep(svg) {
	width: 18px;
	height: 18px;
}

.egc-topbar2__avatar {
	display: flex;
	align-items: center;
	margin-left: 4px;
}
</style>
