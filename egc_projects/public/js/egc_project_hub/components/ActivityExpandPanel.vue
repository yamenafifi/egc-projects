<!-- Inline "drop down and showcase what's underneath" panel for one Activities-table row
     (Procore-style: the linked Submittals/Documents/Dependencies for an Activity are visible
     without navigating away from the list — ActivityDetail.vue's drawer remains the place to
     actually edit an Activity, reached via the "Open" link this panel exposes).

     Reuses get_activity_detail (the same call ActivityDetail.vue makes) and
     ActivityLinkedRecords.vue (the same list it already renders per link_doctype) — this is
     purely a different, inline shell around data the app already fetches and displays. A small
     "tools" strip (mirroring Procore's own per-record tool switcher) lets a Project Manager flip
     between what's underneath an Activity without the panel growing to show everything stacked
     at once; each tool's badge count is available immediately from `linkCounts` (already fetched
     for the whole table in one query — see api/hub.py's get_activities), before the per-Activity
     detail round trip even resolves. -->
<script setup>
import { computed, ref, watch } from "vue";
import { get_activity_detail } from "./activities_api";
import LoadingState from "./LoadingState.vue";
import ErrorState from "./ErrorState.vue";
import EmptyState from "./EmptyState.vue";
import StatusPill from "./StatusPill.vue";
import ActivityLinkedRecords from "./ActivityLinkedRecords.vue";

const props = defineProps({
	activity: { type: String, required: true },
	project: { type: String, required: true },
	canWrite: { type: Boolean, default: false },
	linkCounts: { type: Object, default: () => ({}) },
});
const emit = defineEmits(["open-detail", "changed"]);

const data = ref(null);
const loading = ref(true);
const error = ref(null);

async function load() {
	loading.value = true;
	error.value = null;
	try {
		data.value = await get_activity_detail(props.activity);
	} catch (e) {
		error.value = e.message;
	} finally {
		loading.value = false;
	}
}

watch(() => props.activity, load, { immediate: true });

function reload() {
	load();
	emit("changed");
}

const submittal_links = computed(() => (data.value?.links || []).filter((row) => row.link_doctype === "EGC Submittal"));
const document_links = computed(() =>
	(data.value?.links || []).filter((row) => row.link_doctype === "EGC Project Document")
);
const dependencies = computed(() => data.value?.dependencies || { predecessors: [], successors: [] });
const dependency_count = computed(() => dependencies.value.predecessors.length + dependencies.value.successors.length);

// Badge counts are immediately available from the table's own batched query (props.linkCounts),
// so the strip renders real numbers before the per-Activity round trip above resolves; once it
// does, the actual filtered arrays take over (a link added/removed via this panel is reflected
// without waiting on the parent table's own next reload).
const submittal_count = computed(() =>
	data.value ? submittal_links.value.length : props.linkCounts["EGC Submittal"] || 0
);
const document_count = computed(() =>
	data.value ? document_links.value.length : props.linkCounts["EGC Project Document"] || 0
);

const TOOLS = [
	{ key: "submittals", label: __("Submittals") },
	{ key: "documents", label: __("Drawings & Documents") },
	{ key: "dependencies", label: __("Dependencies") },
];

// Opens on whichever tool actually has something to show — the most useful view first, matching
// what a Project Manager scanning the list is most likely looking for.
const active_tool = ref(
	props.linkCounts["EGC Submittal"]
		? "submittals"
		: props.linkCounts["EGC Project Document"]
			? "documents"
			: "submittals"
);

function tool_count(key) {
	if (key === "submittals") return submittal_count.value;
	if (key === "documents") return document_count.value;
	return dependency_count.value;
}

function open_activity(name) {
	emit("open-detail", name);
}
</script>

<template>
	<div class="activity-expand">
		<LoadingState v-if="loading" :rows="2" />
		<ErrorState v-else-if="error" :message="error" @retry="load" />

		<template v-else-if="data">
			<div class="activity-expand__tools">
				<button
					v-for="tool in TOOLS"
					:key="tool.key"
					type="button"
					class="activity-expand__tool"
					:class="{ 'activity-expand__tool--active': active_tool === tool.key }"
					@click="active_tool = tool.key"
				>
					{{ tool.label }}
					<span class="activity-expand__badge">{{ tool_count(tool.key) }}</span>
				</button>
				<a href="#" class="hub-link activity-expand__open" @click.prevent="open_activity(activity)">
					{{ __("Open full detail") }}
				</a>
			</div>

			<div class="activity-expand__body">
				<ActivityLinkedRecords
					v-if="active_tool === 'submittals'"
					:activity="activity"
					:project="project"
					link-doctype="EGC Submittal"
					:title="__('Submittals')"
					:empty-message="__('No linked submittals yet')"
					:rows="submittal_links"
					:can-write="canWrite"
					@changed="reload"
				/>

				<ActivityLinkedRecords
					v-else-if="active_tool === 'documents'"
					:activity="activity"
					:project="project"
					link-doctype="EGC Project Document"
					:title="__('Drawings & Documents')"
					:empty-message="__('No linked documents yet')"
					:rows="document_links"
					:can-write="canWrite"
					@changed="reload"
				/>

				<div v-else class="activity-expand__deps">
					<div class="activity-expand__dep-group">
						<div class="activity-expand__dep-label">{{ __("Predecessors") }}</div>
						<EmptyState v-if="!dependencies.predecessors.length" :title="__('None')" />
						<ul v-else class="activity-detail__list">
							<li v-for="dep in dependencies.predecessors" :key="dep.name">
								<a href="#" class="activity-detail__link" @click.prevent="open_activity(dep.activity)">
									{{ dep.activity_code }}: {{ dep.activity_name }}
								</a>
								<div class="activity-links__meta">
									<StatusPill :status="dep.status" />
									<span class="activity-detail__dep-type">{{ dep.dependency_type }}</span>
								</div>
							</li>
						</ul>
					</div>
					<div class="activity-expand__dep-group">
						<div class="activity-expand__dep-label">{{ __("Successors") }}</div>
						<EmptyState v-if="!dependencies.successors.length" :title="__('None')" />
						<ul v-else class="activity-detail__list">
							<li v-for="dep in dependencies.successors" :key="dep.name">
								<a href="#" class="activity-detail__link" @click.prevent="open_activity(dep.activity)">
									{{ dep.activity_code }}: {{ dep.activity_name }}
								</a>
								<div class="activity-links__meta">
									<StatusPill :status="dep.status" />
									<span class="activity-detail__dep-type">{{ dep.dependency_type }}</span>
								</div>
							</li>
						</ul>
					</div>
				</div>
			</div>
		</template>
	</div>
</template>

<style scoped>
.activity-expand {
	padding: 14px 18px 18px 46px;
	background: var(--subtle-fg, var(--control-bg));
	border-top: 1px solid var(--border-color);
	border-bottom: 1px solid var(--border-color);
}

.activity-expand__tools {
	display: flex;
	align-items: center;
	gap: 4px;
	margin-bottom: 12px;
	border-bottom: 1px solid var(--border-color);
}

.activity-expand__tool {
	appearance: none;
	border: none;
	background: none;
	padding: 8px 12px;
	font-size: var(--text-sm);
	color: var(--text-muted);
	cursor: pointer;
	border-bottom: 2px solid transparent;
	margin-bottom: -1px;
	display: flex;
	align-items: center;
	gap: 6px;
}

.activity-expand__tool:hover {
	color: var(--text-color);
}

.activity-expand__tool--active {
	color: var(--text-color);
	font-weight: 600;
	border-bottom-color: var(--dark-green-500, var(--green-500));
}

.activity-expand__badge {
	font-size: var(--text-xs);
	color: var(--text-muted);
	background: var(--control-bg);
	border-radius: var(--border-radius-full);
	padding: 0 6px;
	min-width: 18px;
	text-align: center;
}

.activity-expand__tool--active .activity-expand__badge {
	background: var(--fg-color);
}

.activity-expand__open {
	margin-left: auto;
	font-size: var(--text-xs);
	white-space: nowrap;
	padding: 0 4px 8px;
}

.activity-expand__deps {
	display: flex;
	flex-direction: column;
	gap: 14px;
}

.activity-expand__dep-label {
	font-size: var(--text-xs);
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.02em;
	margin-bottom: 6px;
}

.hub-link {
	color: var(--text-color);
	cursor: pointer;
	text-decoration: none;
	border-bottom: 1px dashed var(--border-color);
}

.hub-link:hover {
	color: var(--text-color);
	border-bottom-color: var(--text-color);
}

.activity-detail__list {
	list-style: none;
	margin: 0;
	padding: 0;
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.activity-detail__list li {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 10px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius);
	padding: 8px 12px;
	background: var(--fg-color);
}

.activity-detail__link {
	color: var(--text-color);
	font-weight: 500;
}

.activity-detail__dep-type {
	font-size: var(--text-xs);
	color: var(--text-muted);
}

.activity-links__meta {
	display: flex;
	align-items: center;
	gap: 8px;
	flex: 0 0 auto;
}
</style>
