// Workflow Template management — the missing UI for `EGC Submittal Workflow Template`. Before
// this, `create_workflow_template` existed as a whitelisted endpoint but nothing in the Hub ever
// called it: a template could only be built or edited on the raw Frappe desk form, and
// SubmittalDetail.vue's own empty-state message told the user to go there. This is the one place
// in the Hub a template's stage sequence is authored, previewed, and edited — direct fix for
// "I never saw the configuration for this sequence."
//
// Templates are global (no `project` field on the doctype), so this flow is not project-scoped —
// any project's Submittal review can apply any template.

import {
	get_workflow_templates,
	get_workflow_template_detail,
	create_workflow_template,
	update_workflow_template,
	delete_workflow_template,
} from "./submittals_api";

function _stages_from_steps(steps) {
	const by_sequence = {};
	for (const step of steps) {
		(by_sequence[step.sequence] = by_sequence[step.sequence] || []).push(step);
	}
	return Object.keys(by_sequence)
		.map(Number)
		.sort((a, b) => a - b)
		.map((sequence) => ({ sequence, steps: by_sequence[sequence] }));
}

/** Read-only ordered stage list — reused by SubmittalDetail.vue/submit_for_review_flow.js's
 * "Apply Workflow Template" preview, and by this module's own edit dialog before edits start. */
export function renderStagesPreviewHtml(steps) {
	if (!steps.length) {
		return `<p class="text-muted">${__("This template has no stages yet.")}</p>`;
	}
	const stages = _stages_from_steps(steps);
	return `<ol class="workflow-template-preview" style="padding-left:18px;margin:0;">${stages
		.map(
			(stage) => `<li style="margin-bottom:8px;">
				<strong>${__("Stage {0}", [stage.sequence])}</strong>
				<ul style="margin:2px 0 0;padding-left:18px;">
					${stage.steps
						.map(
							(step) =>
								`<li style="display:flex;align-items:center;gap:4px;">${frappe.utils.escape_html(step.label || step.reviewer_role || __("(role not set)"))}${
									step.is_required ? "" : ` <em>(${__("optional")})</em>`
								}</li>`
						)
						.join("")}
				</ul>
			</li>`
		)
		.join("")}</ol>`;
}

function _open_add_step_dialog(local_steps, on_added) {
	const existing_sequences = local_steps.map((s) => s.sequence);
	const next_sequence = existing_sequences.length ? Math.max(...existing_sequences) : 1;

	const dialog = new frappe.ui.Dialog({
		title: __("Add Stage"),
		fields: [
			{
				fieldname: "sequence",
				fieldtype: "Int",
				label: __("Stage"),
				default: next_sequence,
				reqd: 1,
				description: __(
					"Reviewers sharing the same stage number review in parallel. Use the next stage number to review after the current stage responds instead."
				),
			},
			{ fieldname: "reviewer_role", fieldtype: "Link", label: __("Reviewer Role"), options: "EGC Stakeholder Role", reqd: 1 },
			{ fieldname: "label", fieldtype: "Data", label: __("Display Label"), description: __("Optional — falls back to the role name.") },
			{ fieldname: "is_required", fieldtype: "Check", label: __("Required"), default: 1 },
		],
		primary_action_label: __("Add"),
		primary_action(values) {
			on_added({
				sequence: values.sequence,
				reviewer_role: values.reviewer_role,
				label: values.label || null,
				is_required: values.is_required ? 1 : 0,
			});
			dialog.hide();
		},
	});
	dialog.show();
}

// Re-renders the stage list with an inline remove control per step. renderStagesPreviewHtml
// itself stays a pure read-only formatter (shared with the read-only "Apply Template" preview,
// which must never show remove controls), so this walks the same stage/step structure afterward
// and appends one "Remove" control per step line.
function _bind_remove_buttons($wrapper, local_steps, render_steps) {
	const stages = _stages_from_steps(local_steps);
	const $stage_items = $wrapper.find(".workflow-template-preview > li");
	stages.forEach((stage, stage_index) => {
		const $step_items = $stage_items.eq(stage_index).find("> ul > li");
		stage.steps.forEach((step, step_index) => {
			const $remove = $(
				`<button type="button" class="btn-link text-danger" style="margin-left:8px;font-size:var(--text-xs);">${__("Remove")}</button>`
			);
			$remove.on("click", () => {
				const target = local_steps.indexOf(step);
				if (target > -1) local_steps.splice(target, 1);
				render_steps();
			});
			$step_items.eq(step_index).append($remove);
		});
	});
}

function _open_template_details_dialog(existing, { onSaved }) {
	// Edited entirely in memory; only written via create_workflow_template/update_workflow_template
	// once "Save" is pressed — matches the rest of the Hub's dialog-commits-on-primary-action style.
	let local_steps = existing ? existing.steps.map((s) => ({ ...s })) : [];

	const dialog = new frappe.ui.Dialog({
		title: existing ? __("Edit Workflow Template") : __("New Workflow Template"),
		size: "large",
		fields: [
			{ fieldname: "template_name", fieldtype: "Data", label: __("Template Name"), reqd: 1, default: existing?.template_name },
			{ fieldname: "description", fieldtype: "Small Text", label: __("Description"), default: existing?.description },
			{ fieldtype: "Section Break", label: __("Stages") },
			{ fieldname: "steps_preview", fieldtype: "HTML" },
			{
				fieldname: "add_step",
				fieldtype: "Button",
				label: __("+ Add Stage"),
				click: () =>
					_open_add_step_dialog(local_steps, (step) => {
						local_steps.push(step);
						render_steps();
					}),
			},
		],
		primary_action_label: __("Save"),
		primary_action(values) {
			if (!local_steps.length) {
				frappe.msgprint({
					title: __("Add at Least One Stage"),
					message: __("A template with no stages has nothing to apply."),
					indicator: "orange",
				});
				return;
			}
			dialog.disable_primary_action();
			const call = existing
				? update_workflow_template(existing.name, values.template_name, values.description, local_steps)
				: create_workflow_template(values.template_name, local_steps, values.description);
			call
				.then(() => {
					dialog.hide();
					onSaved();
				})
				.catch((e) => {
					dialog.enable_primary_action();
					frappe.msgprint({ title: __("Could Not Save Template"), message: e.message, indicator: "red" });
				});
		},
	});

	function render_steps() {
		const $wrapper = dialog.fields_dict.steps_preview.$wrapper;
		const hint = local_steps.length
			? `<div class="text-muted" style="margin-top:6px;font-size:var(--text-xs);">${__("Each stage's Remove link deletes just that reviewer.")}</div>`
			: "";
		$wrapper.html(renderStagesPreviewHtml(local_steps) + hint);
		_bind_remove_buttons($wrapper, local_steps, render_steps);
	}

	render_steps();
	dialog.show();
}

export function openManageWorkflowTemplatesFlow({ onChanged } = {}) {
	let templates = [];

	const dialog = new frappe.ui.Dialog({
		title: __("Workflow Templates"),
		size: "large",
		fields: [{ fieldname: "list", fieldtype: "HTML" }],
	});

	function render_list() {
		const $wrapper = dialog.fields_dict.list.$wrapper;
		if (!templates.length) {
			$wrapper.html(`<p class="text-muted">${__("No workflow templates yet.")}</p>`);
		} else {
			$wrapper.html(
				templates
					.map(
						(t) => `<div data-template="${frappe.utils.escape_html(t.name)}" style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--border-color);">
							<div>
								<strong>${frappe.utils.escape_html(t.template_name)}</strong>
								${t.description ? `<div class="text-muted" style="font-size:var(--text-xs);">${frappe.utils.escape_html(t.description)}</div>` : ""}
							</div>
							<div style="flex-shrink:0;">
								<button type="button" class="btn btn-xs btn-default workflow-template-list__edit">${__("Edit")}</button>
								<button type="button" class="btn btn-xs btn-default text-danger workflow-template-list__delete">${__("Delete")}</button>
							</div>
						</div>`
					)
					.join("")
			);
		}
		$wrapper.find(".workflow-template-list__edit").on("click", function () {
			const name = $(this).closest("[data-template]").data("template");
			get_workflow_template_detail(name).then((detail) => {
				_open_template_details_dialog(detail, { onSaved: reload });
			});
		});
		$wrapper.find(".workflow-template-list__delete").on("click", function () {
			const name = $(this).closest("[data-template]").data("template");
			frappe.confirm(
				__("Delete this workflow template? Submissions that already used it keep their own steps unchanged."),
				() => {
					delete_workflow_template(name)
						.then(reload)
						.catch((e) => frappe.msgprint({ title: __("Could Not Delete"), message: e.message, indicator: "red" }));
				}
			);
		});
	}

	function reload() {
		get_workflow_templates().then((rows) => {
			templates = rows;
			render_list();
			onChanged && onChanged();
		});
	}

	dialog.set_primary_action(__("+ New Template"), () => {
		_open_template_details_dialog(null, { onSaved: reload });
	});
	dialog.show();
	reload();
}
