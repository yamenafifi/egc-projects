<!-- Renders the header's capped stakeholder subset (ARCHITECTURE_V2.md §4 —
`context.profile.key_stakeholders`, already capped server-side to a header-relevant subset).
Purely presentational: it never fetches the full stakeholder list itself (that is
`get_project_profile()`, consumed by the Project Information tab, not this header). -->
<script setup>
defineProps({
	stakeholders: { type: Array, default: () => [] },
});

function display_role(row) {
	return row.role_label || row.role || "";
}

function display_party(row) {
	// An internal role (EGC Project Manager, Site Manager, …) resolves to a Frappe user —
	// prefer their name over the raw party_name once one is known.
	return row.user_full_name || row.party_name || "";
}
</script>

<template>
	<div v-if="stakeholders.length" class="hub-stakeholders">
		<span v-for="(row, idx) in stakeholders" :key="(row.role || 'role') + ':' + idx" class="hub-stakeholder-chip">
			<span class="hub-stakeholder-chip__role">{{ display_role(row) }}:</span>
			<span class="hub-stakeholder-chip__name">{{ display_party(row) }}</span>
		</span>
	</div>
</template>

<style scoped>
.hub-stakeholders {
	display: flex;
	flex-wrap: wrap;
	gap: 4px 18px;
	margin-top: 4px;
}

.hub-stakeholder-chip {
	display: inline-flex;
	max-width: 280px;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	font-size: var(--text-sm);
	color: var(--text-color);
}

.hub-stakeholder-chip__role {
	color: var(--text-muted);
	margin-right: 4px;
	flex: 0 0 auto;
}

.hub-stakeholder-chip__name {
	overflow: hidden;
	text-overflow: ellipsis;
}
</style>
