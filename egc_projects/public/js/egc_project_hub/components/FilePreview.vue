<!-- Inline file preview — a direct Vue port of core's own `frappe/core/doctype/file/file.js`
     `preview_file` (image/video/pdf/mp3 detection and markup), so a file previewed inside the Hub
     renders exactly the way it would on the native File form. `.dwg` gets its own branch: no
     browser can render CAD binary natively, so it shows a clear "open in a CAD viewer" state with
     a download action instead of a broken/empty preview — see the component's own note on why
     there is no inline DWG rendering yet. -->
<script setup>
import { computed } from "vue";

const props = defineProps({
	fileUrl: { type: String, required: true },
	fileName: { type: String, default: "" },
});

function extension() {
	const clean = (props.fileName || props.fileUrl).split("?")[0];
	const match = clean.match(/\.([a-z0-9]+)$/i);
	return match ? match[1].toLowerCase() : "";
}

const kind = computed(() => {
	if (frappe.utils.is_image_file(props.fileUrl)) return "image";
	if (frappe.utils.is_video_file(props.fileUrl)) return "video";
	const ext = extension();
	if (ext === "pdf") return "pdf";
	if (ext === "mp3") return "audio";
	if (ext === "dwg") return "dwg";
	return "unsupported";
});

function download() {
	window.open(props.fileUrl, "_blank", "noopener");
}
</script>

<template>
	<div class="file-preview">
		<img v-if="kind === 'image'" class="file-preview__image" :src="fileUrl" :alt="fileName" />

		<video v-else-if="kind === 'video'" class="file-preview__video" controls>
			<source :src="fileUrl" />
			{{ __("Your browser does not support the video element.") }}
		</video>

		<object v-else-if="kind === 'pdf'" class="file-preview__pdf-object" type="application/pdf" :data="fileUrl">
			<embed class="file-preview__pdf-object" :src="fileUrl" type="application/pdf" />
		</object>

		<audio v-else-if="kind === 'audio'" class="file-preview__audio" controls>
			<source :src="fileUrl" type="audio/mpeg" />
			{{ __("Your browser does not support the audio element.") }}
		</audio>

		<div v-else-if="kind === 'dwg'" class="file-preview__unsupported">
			<div class="file-preview__unsupported-title">{{ __("DWG file") }}</div>
			<div class="file-preview__unsupported-note">
				{{ __("This CAD drawing can't be rendered in the browser. Open it in AutoCAD or another DWG viewer.") }}
			</div>
			<button type="button" class="btn btn-xs btn-default" @click="download">{{ __("Download") }}</button>
		</div>

		<div v-else class="file-preview__unsupported">
			<div class="file-preview__unsupported-note">{{ __("No preview available for this file type.") }}</div>
			<button type="button" class="btn btn-xs btn-default" @click="download">{{ __("Download") }}</button>
		</div>
	</div>
</template>

<style scoped>
.file-preview {
	display: flex;
	justify-content: center;
	padding: 12px;
	background: var(--control-bg);
	border-radius: var(--border-radius);
}

.file-preview__image {
	max-width: 100%;
	max-height: 480px;
	border-radius: var(--border-radius);
}

.file-preview__video {
	max-width: 100%;
	max-height: 480px;
}

.file-preview__pdf-object {
	width: 100%;
	height: 600px;
	background: #323639;
	border: none;
}

.file-preview__audio {
	width: 100%;
}

.file-preview__unsupported {
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 8px;
	padding: 24px 12px;
	text-align: center;
}

.file-preview__unsupported-title {
	font-weight: 600;
	color: var(--text-color);
}

.file-preview__unsupported-note {
	font-size: var(--text-sm);
	color: var(--text-muted);
	max-width: 360px;
}
</style>
