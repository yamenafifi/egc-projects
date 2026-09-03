<!-- Shared comment composer for Submittal/Document/Activity detail pages — replaces each page's
     own plain `<textarea v-model="new_comment">` with one that supports @mentioning anyone on
     this project's own Directory, the same "Directory people STRICTLY" scoping every other
     person-picker in this app already uses (directory_helpers.js) rather than the whole site's
     User list.

     A contenteditable div, not a textarea: a mention needs to render as an atomic, non-editable
     chip inline with typed text, which a textarea (plain characters only) can't do. Kept
     deliberately narrow in what it can ever contain — plain text, `<br>` line breaks, and this
     component's own mention chips — so serialize() below can convert it into Comment content
     without needing a general-purpose HTML sanitizer: paste is forced to plain text, and a
     mention chip is the only element this component ever inserts.

     Emits the built content string on submit; the parent still owns the actual add_comment()
     call and its own error handling, exactly like each page's `do_post_comment` already does for
     the textarea today — this component only replaces how that content string gets built.
     `clear()` is exposed so the parent can empty the box once the post actually succeeds
     (mirroring the existing `new_comment.value = ""` placement, after the await, not before). -->
<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { get_directory } from "./directory_api";

const props = defineProps({
	project: { type: String, default: null },
	posting: { type: Boolean, default: false },
	placeholder: { type: String, default: "" },
});
const emit = defineEmits(["submit"]);

const editorRef = ref(null);
const has_content = ref(false);

// -- mention candidates: this project's own Directory, restricted to rows that already have a
// real login (`person`) — a stakeholder with no User can't receive an in-app mention anyway. --

const directory_rows = ref([]);
watch(
	() => props.project,
	async (project) => {
		if (!project) {
			directory_rows.value = [];
			return;
		}
		const rows = await get_directory(project).catch(() => []);
		directory_rows.value = rows.filter((r) => r.person);
	},
	{ immediate: true }
);

// -- @mention detection: re-evaluated on every input against the caret's own text node, not
// tracked as a running "am I in mention mode" flag — simpler and self-correcting (typing a space,
// clicking elsewhere, or deleting the @ all naturally fall out of it on the very next input). --

const mention_query = ref(null); // null = not currently typing a mention
const mention_range = ref(null); // the Range spanning "@query" — replaced with a chip on pick
const active_index = ref(0);

const filtered_candidates = computed(() => {
	if (mention_query.value === null) return [];
	const q = mention_query.value.toLowerCase();
	return directory_rows.value
		.filter((r) => (r.party_name || "").toLowerCase().includes(q) || r.person.toLowerCase().includes(q))
		.slice(0, 8);
});

watch(filtered_candidates, () => {
	active_index.value = 0;
});

function close_mentions() {
	mention_query.value = null;
	mention_range.value = null;
}

function on_input() {
	has_content.value = !!editorRef.value && editorRef.value.textContent.trim().length > 0;

	const sel = window.getSelection();
	if (!sel || !sel.rangeCount || !sel.isCollapsed) return close_mentions();
	const range = sel.getRangeAt(0);
	const node = range.startContainer;
	if (node.nodeType !== Node.TEXT_NODE || !editorRef.value.contains(node)) return close_mentions();

	// An "@" run with no whitespace since it started, immediately before the caret — the same
	// shape every chat/issue-tracker mention trigger uses.
	const text_before = node.textContent.slice(0, range.startOffset);
	const match = /(?:^|\s)@([^\s@]*)$/.exec(text_before);
	if (!match) return close_mentions();

	const query = match[1];
	const at_offset = text_before.length - query.length - 1;
	const query_range = document.createRange();
	query_range.setStart(node, at_offset);
	query_range.setEnd(node, range.startOffset);
	mention_range.value = query_range;
	mention_query.value = query;
}

function pick_mention(candidate) {
	const range = mention_range.value;
	if (!range) return;
	range.deleteContents();

	const chip = document.createElement("span");
	chip.contentEditable = "false";
	chip.className = "hub-mention-box__chip";
	chip.dataset.id = candidate.person;
	chip.textContent = `@${candidate.party_name || candidate.person}`;
	range.insertNode(chip);

	// A trailing plain space, not part of the chip — keeps subsequent typing in a fresh text
	// node (so a second "@" right after isn't mistaken for still being inside this mention) and
	// gives the caret somewhere to land.
	const space = document.createTextNode(" ");
	chip.after(space);

	const new_range = document.createRange();
	new_range.setStartAfter(space);
	new_range.collapse(true);
	const sel = window.getSelection();
	sel.removeAllRanges();
	sel.addRange(new_range);

	close_mentions();
	has_content.value = true;
	editorRef.value.focus();
}

function on_keydown(e) {
	if (mention_query.value !== null && filtered_candidates.value.length) {
		if (e.key === "ArrowDown") {
			e.preventDefault();
			active_index.value = Math.min(active_index.value + 1, filtered_candidates.value.length - 1);
			return;
		}
		if (e.key === "ArrowUp") {
			e.preventDefault();
			active_index.value = Math.max(active_index.value - 1, 0);
			return;
		}
		if (e.key === "Enter" || e.key === "Tab") {
			e.preventDefault();
			pick_mention(filtered_candidates.value[active_index.value]);
			return;
		}
	}
	if (mention_query.value !== null && e.key === "Escape") {
		e.preventDefault();
		close_mentions();
		return;
	}
}

// Plain text only — this component's serialize() below only ever expects text, <br>, and its
// own mention chips; letting pasted HTML through would break that assumption (and could smuggle
// arbitrary markup into what mention_render.js later has to treat as trusted-shape content).
function on_paste(e) {
	e.preventDefault();
	const text = (e.clipboardData || window.clipboardData).getData("text/plain");
	document.execCommand("insertText", false, text);
}

onMounted(() => {
	// Makes a plain Enter insert a <br> instead of the browser's default per-engine paragraph
	// wrapping (a <div> in Chrome/Safari, a <br> in Firefox) — keeps serialize() below simple and
	// predictable across browsers. Still functional everywhere despite being nominally
	// "deprecated"; there is no successor API for this specific normalization.
	try {
		document.execCommand("defaultParagraphSeparator", false, "br");
	} catch {
		// Best-effort only — worst case Enter falls back to the browser's own default, which
		// serialize()'s DIV/P fallback below already handles without losing content.
	}
});

function escape_text(s) {
	return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Walks the editor's own DOM (never innerHTML string-parsed — this only ever needs to understand
// nodes it created itself) into the plain-text-plus-real-mention-spans shape comments.py stores
// and mention_render.js's own escape-then-reinject renderer expects back.
function serialize() {
	let out = "";
	function walk(node) {
		if (node.nodeType === Node.TEXT_NODE) {
			// Escaped here, deliberately: Comment.validate() (Frappe core) runs `sanitize_html()`
			// on every save, old comments and new alike — a real HTML parser (nh3), not a no-op.
			// Sending typed text un-escaped hands that parser literal "<"/"&" characters it then
			// has to interpret AS HTML on its own terms: text that happens to look like a real,
			// allowed tag (nh3's allowlist includes basic formatting — b, i, span, br, ...)
			// silently becomes real markup, while a stray "<" that doesn't parse as one gets
			// re-escaped on the way back out — the same input treated two different ways
			// depending on what follows it (confirmed directly: typing "<i>text</i>" survived as
			// a real `<i>` element while "a < b" came back as "a &lt; b"). Escaping first removes
			// the ambiguity entirely — every escaped entity decodes to inert text data during
			// parsing and gets re-escaped identically on the way out, so typed text always stays
			// exactly what was typed. Only this component's own mention span (inserted as real
			// tag syntax below, never through a text node) is meant to survive as real markup.
			out += escape_text(node.textContent);
			return;
		}
		if (node.nodeType !== Node.ELEMENT_NODE) return;
		if (node.tagName === "BR") {
			out += "\n";
			return;
		}
		if (node.classList && node.classList.contains("hub-mention-box__chip")) {
			out += `<span class="mention" data-id="${escape_text(node.dataset.id || "")}">${escape_text(node.textContent || "")}</span>`;
			return;
		}
		// Defensive fallback for a stray block element (e.g. an engine's own default Enter
		// behavior slipping past the normalization above) — treat it as its own line rather than
		// silently losing or merging its content.
		if (node.tagName === "DIV" || node.tagName === "P") {
			if (out && !out.endsWith("\n")) out += "\n";
			for (const child of node.childNodes) walk(child);
			return;
		}
		for (const child of node.childNodes) walk(child);
	}
	for (const child of editorRef.value.childNodes) walk(child);
	return out;
}

function handle_submit() {
	const content = serialize();
	if (!content.trim() || props.posting) return;
	emit("submit", content);
}

function clear() {
	if (editorRef.value) editorRef.value.innerHTML = "";
	has_content.value = false;
	close_mentions();
}

defineExpose({ clear });
</script>

<template>
	<div class="hub-mention-box">
		<div
			ref="editorRef"
			class="form-control hub-mention-box__editor"
			contenteditable="true"
			:data-placeholder="placeholder"
			@input="on_input"
			@keydown="on_keydown"
			@paste="on_paste"
			@blur="close_mentions"
		></div>

		<div v-if="mention_query !== null && filtered_candidates.length" class="hub-mention-box__suggestions">
			<button
				v-for="(candidate, index) in filtered_candidates"
				:key="candidate.person"
				type="button"
				class="hub-mention-box__suggestion"
				:class="{ 'hub-mention-box__suggestion--active': index === active_index }"
				@mousedown.prevent="pick_mention(candidate)"
			>
				<strong>{{ candidate.party_name || candidate.person }}</strong>
				<span v-if="candidate.party_name">{{ candidate.person }}</span>
			</button>
		</div>

		<button type="button" class="btn btn-sm btn-primary hub-mention-box__submit" :disabled="posting || !has_content" @click="handle_submit">
			{{ __("Post") }}
		</button>
	</div>
</template>
