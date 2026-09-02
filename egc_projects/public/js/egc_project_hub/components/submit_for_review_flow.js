// The ONE "submit a document for review" flow (docs/ARCHITECTURE_V2.md's Documents/Submittals
// redesign) — used from every place that used to be a separate dialog:
//   - DocumentDetail.vue's "Submit for Review" button (single document, preset and locked)
//   - SubmittalsTab.vue's "+ New Submittal" button (document picker, since there's no document
//     context to preset yet)
//   - SubmittalDetail.vue's empty state for a Submittal that exists (e.g. created via the raw
//     native form) but has no submission cycle yet — `existingSubmittal` skips the identity
//     fields and the create_submittal() call, since the record is already there.
//
// The old DocumentDetail flow created the Submittal shell and told the user to "add the
// reviewer(s) from its own page" — it never offered a review approach at all. The old
// SubmittalsTab → "Start Submission" flow asked for the full review setup but never referenced
// a Document at creation time. This module is all three, unified: identity fields (skipped when
// the Submittal already exists), a document picker (or a locked preset), and the same
// ad-hoc-or-template review setup every time — so getting a document into review always starts
// from "I have a document, I'm submitting it," never from a bare, document-less form.
//
// Error handling mirrors SubmittalDetail.vue's original `open_start_submission_dialog` exactly:
// once the Submittal (or its first submission) exists, a later step failing must never be
// reported as though nothing happened — surfaced as an orange "created, but incomplete" message
// with the record still handed back via `onCreated`, not a red failure that leaves the caller
// thinking nothing was created.

import {
	create_submittal,
	create_first_submission,
	add_submission_document,
	get_documents_with_current_revision,
	get_workflow_templates,
	get_workflow_template_detail,
	apply_workflow_template,
	add_review_step,
	submit_submission,
} from "./submittals_api";
import { renderStagesPreviewHtml } from "./workflow_template_flow";
import {
	get_directory_person_emails,
	get_directory_organization_names,
	person_link_filter,
	organization_link_filter,
} from "./directory_helpers";
import { suggest_submittal_code } from "./code_naming_api";
import { apply_suggested_code } from "./code_naming_helpers";

//: everything `api/submittals.py.create_submittal`'s own `_CREATE_FIELDS` allow-list accepts
//: beyond identity (submittal_number/title/submittal_type/discipline) — kept in an optional,
//: collapsed section rather than dropped: this is the exact field set SubmittalsTab.vue's
//: pre-unification "+ New Submittal" dialog captured at creation time, and none of it should be
//: silently lost just because creation now also asks about documents/review. `responsible_party`/
//: `received_from` (the free-text fallbacks their Directory-linked siblings used to mirror into)
//: are deliberately NOT in this list any more — direct user instruction: every party field in
//: this form is strictly a Project Directory pick, no free-text escape hatch, matching the same
//: change made to Documents' Originator field.
const _ADDITIONAL_DETAIL_FIELDNAMES = ["wbs_node", "responsible_organization", "received_from_person", "submittal_manager", "description"];

//: Direct user instruction: "I shouldn't have to assign what type of submittal it is" — a
//: Document's own `document_type` and a Submittal's `submittal_type` are separate master lists
//: with no formal link between them, but this app's own demo data shows most of them already
//: share an exact name (Calculation, Method Statement, Technical Data, ...); "Drawing" is the one
//: common exception (its submittal-side equivalent is named "Shop Drawing"). Matched by exact
//: name first, this alias second, and left for the user to pick only when neither resolves — a
//: guessed Link value that doesn't exist would just fail `create_submittal` outright, which is
//: worse than asking.
const _DOCUMENT_TO_SUBMITTAL_TYPE_ALIASES = { Drawing: "Shop Drawing" };

function _infer_submittal_type(documents, submittal_type_names) {
	for (const doc of documents) {
		if (!doc.document_type) continue;
		if (submittal_type_names.has(doc.document_type)) return doc.document_type;
		const alias = _DOCUMENT_TO_SUBMITTAL_TYPE_ALIASES[doc.document_type];
		if (alias && submittal_type_names.has(alias)) return alias;
	}
	return null;
}

/**
 * @param {Object} opts
 * @param {string} opts.project
 * @param {{name: string, label: string}|null} [opts.presetDocument] - when set (launched from a
 *   Document's own page), the document field is a locked display instead of a picker.
 * @param {string|null} [opts.existingSubmittal] - when set, the Submittal already exists (e.g.
 *   created via the native form with no submission yet) — the identity fields and the
 *   create_submittal() call are both skipped, and this flow only creates its FIRST submission.
 * @param {Object} [opts.defaults] - default values for submittal_number/title/submittal_type/discipline
 *   (ignored when existingSubmittal is set).
 * @param {(submittalName: string, info: {needsReviewers: boolean}) => void} [opts.onCreated] -
 *   called once the Submittal exists (even on partial failure) so the caller can navigate to it /
 *   refresh its own view. `needsReviewers` is only ever true on the "created, but incomplete"
 *   partial-failure path now — the happy path always ends fully submitted with reviewers already
 *   assigned, never a Draft left for the caller to finish configuring.
 */
export async function openSubmitForReviewFlow({
	project,
	presetDocument = null,
	existingSubmittal = null,
	defaults = {},
	onCreated,
} = {}) {
	let templates = [];
	try {
		templates = await get_workflow_templates();
	} catch (e) {
		// Non-fatal — the ad-hoc reviewer path still works with no templates defined.
	}
	const approach_options = templates.length ? ["Ad-hoc reviewer(s)", "Apply a workflow template"] : ["Ad-hoc reviewer(s)"];

	// Fetched up front (not per-field) so every Link-to-Directory field below is filtered from
	// first render — direct user instruction: "STRICTLY" from the Project Directory, never a
	// free-typed one-off party. `submittal_type_names` feeds `_infer_submittal_type` — direct user
	// instruction: "I shouldn't have to assign what type of submittal it is."
	const [directory_emails, directory_orgs, submittal_type_names] = existingSubmittal
		? [[], [], new Set()]
		: await Promise.all([
				get_directory_person_emails(project),
				get_directory_organization_names(project),
				frappe.db.get_list("EGC Submittal Type", { fields: ["name"], limit: 0 }).then((rows) => new Set(rows.map((r) => r.name))),
			]);

	const fields = [];
	if (presetDocument) {
		fields.push({
			fieldname: "document_display",
			fieldtype: "Data",
			label: __("Document"),
			default: presetDocument.label,
			read_only: 1,
		});
	} else {
		fields.push({
			fieldname: "documents",
			fieldtype: "MultiSelectPills",
			label: __("Documents"),
			reqd: 1,
			description: __(
				"Pick the document(s) this is about — the current issued revision of each is used automatically. You never pick a revision directly."
			),
			get_data: (txt) =>
				frappe.db.get_link_options("EGC Project Document", txt, {
					project,
					document_status: "Issued",
				}),
		});
	}

	if (!existingSubmittal) {
		fields.push(
			{
				fieldname: "submittal_number",
				fieldtype: "Data",
				label: __("Submittal Number"),
				reqd: 1,
				read_only: 1,
				default: defaults.submittal_number,
				description: __(
					"Generated automatically from Type + Discipline — pick Discipline below; Type can be left blank to detect it from the document's own type."
				),
			},
			{ fieldname: "title", fieldtype: "Data", label: __("Title"), reqd: 1, default: defaults.title },
			{ fieldtype: "Column Break" },
			{
				fieldname: "submittal_type",
				fieldtype: "Link",
				options: "EGC Submittal Type",
				label: __("Type"),
				default: defaults.submittal_type,
				description: __("Detected from the document's own type when left blank."),
				onchange: () => suggest_submittal_number(dialog, project),
			},
			{
				fieldname: "discipline",
				fieldtype: "Link",
				options: "EGC Discipline",
				label: __("Discipline"),
				default: defaults.discipline,
				reqd: 1,
				onchange: () => suggest_submittal_number(dialog, project),
			},
			{ fieldtype: "Section Break", label: __("Additional Details"), collapsible: 1 },
			{
				fieldname: "wbs_node",
				fieldtype: "Link",
				label: __("WBS Node"),
				options: "EGC WBS Node",
				get_query: () => ({ filters: { project } }),
			},
			{
				fieldname: "submittal_manager",
				fieldtype: "Link",
				label: __("Submittal Manager"),
				options: "User",
				description: __("Must already be on this project's Directory."),
				get_query: person_link_filter(directory_emails),
			},
			{ fieldtype: "Column Break" },
			{
				fieldname: "responsible_organization",
				fieldtype: "Link",
				label: __("Responsible Organization"),
				options: "Customer",
				description: __("Must already be on this project's Directory."),
				get_query: organization_link_filter(directory_orgs),
			},
			{
				fieldname: "received_from_person",
				fieldtype: "Link",
				label: __("Received From"),
				options: "User",
				description: __("Must already be on this project's Directory."),
				get_query: person_link_filter(directory_emails),
			},
			{ fieldtype: "Column Break" },
			{ fieldname: "description", fieldtype: "Small Text", label: __("Description") }
		);
	}

	fields.push(
		{ fieldtype: "Section Break", label: __("Review") },
		{
			fieldname: "review_approach",
			fieldtype: "Select",
			label: __("Review Approach"),
			options: approach_options,
			default: approach_options[0],
			reqd: 1,
		},
		{
			// Collected right here, inline — never a separate follow-up dialog after creation.
			// Every reviewer responds in one parallel stage (sequence 1); anything more staged
			// than that is exactly what a workflow template is for.
			fieldname: "reviewers",
			fieldtype: "MultiSelectPills",
			label: __("Reviewer(s)"),
			depends_on: 'eval:doc.review_approach == "Ad-hoc reviewer(s)"',
			mandatory_depends_on: 'eval:doc.review_approach == "Ad-hoc reviewer(s)"',
			description: __("Must already be on this project's Directory."),
			get_data: (txt) =>
				frappe.db.get_link_options("User", txt, {
					name: ["in", directory_emails.length ? directory_emails : ["__none__"]],
				}),
		},
		{
			fieldname: "template",
			fieldtype: "Select",
			label: __("Workflow Template"),
			options: templates.map((t) => t.name),
			depends_on: 'eval:doc.review_approach == "Apply a workflow template"',
			mandatory_depends_on: 'eval:doc.review_approach == "Apply a workflow template"',
			onchange: () => preview_template(dialog.get_value("template")),
		},
		{
			fieldname: "template_stages_preview",
			fieldtype: "HTML",
			depends_on: 'eval:doc.review_approach == "Apply a workflow template"',
		}
	);

	function preview_template(name) {
		const field = dialog.fields_dict.template_stages_preview;
		if (!field) return;
		if (!name) {
			field.$wrapper.html("");
			return;
		}
		get_workflow_template_detail(name).then((detail) => {
			field.$wrapper.html(renderStagesPreviewHtml(detail.steps));
		});
	}

	const dialog = new frappe.ui.Dialog({
		title: existingSubmittal ? __("Start Submission") : __("New Submittal"),
		fields,
		primary_action_label: existingSubmittal ? __("Start Submission") : __("Create Submittal"),
		async primary_action(values) {
			dialog.disable_primary_action();
			// Once the Submittal exists (created below, or already existingSubmittal), it's a
			// real row in the database — a later step failing must not be reported as though
			// nothing happened (see module docstring).
			let submittal_name = existingSubmittal;
			try {
				const doc_names = presetDocument ? [presetDocument.name] : values.documents || [];
				if (!doc_names.length) throw new Error(__("At least one document is required."));

				// Belt-and-braces on top of `mandatory_depends_on` above: a MultiSelectPills field
				// with nothing picked is still a truthy `[]`, not the falsy value Frappe's own
				// mandatory check looks for — this is a real Submittal, never one left with nobody
				// assigned to it (module docstring / SubmittalDetail.vue's own comment on this).
				if (values.review_approach !== "Apply a workflow template" && !(values.reviewers || []).length) {
					throw new Error(__("Pick at least one reviewer, or choose a workflow template."));
				}

				const resolved = await get_documents_with_current_revision(project, doc_names);
				const missing = resolved.filter((d) => !d.current_revision);
				if (missing.length) {
					throw new Error(
						__("{0} has no issued revision yet.", [missing.map((d) => d.document_number).join(", ")])
					);
				}

				if (!existingSubmittal) {
					const submittal_type = values.submittal_type || _infer_submittal_type(resolved, submittal_type_names);
					if (!submittal_type) {
						throw new Error(
							__("Couldn't detect a Type from the document; pick one under Additional Details.")
						);
					}
					const create_values = {
						submittal_number: values.submittal_number,
						title: values.title,
						submittal_type,
						discipline: values.discipline,
					};
					for (const fieldname of _ADDITIONAL_DETAIL_FIELDNAMES) {
						if (values[fieldname]) create_values[fieldname] = values[fieldname];
					}
					submittal_name = (await create_submittal(project, create_values)).name;
				}

				const submission_name = (await create_first_submission(submittal_name)).name;
				for (const doc of resolved) {
					await add_submission_document(submission_name, doc.current_revision);
				}

				if (values.review_approach === "Apply a workflow template") {
					await apply_workflow_template(submission_name, values.template);
				} else {
					// Ad-hoc — every reviewer picked above becomes one parallel-stage, required step.
					for (const reviewer of values.reviewers || []) {
						await add_review_step(submission_name, 1, undefined, reviewer, true);
					}
				}

				// Never leave the submission sitting in Draft: reviewers are already assigned above
				// (or resolved from the template), so submitting immediately is what actually puts
				// it in front of them — this is the whole point of "submit for review," not a
				// separate deliberate step the user has to remember to come back for.
				await submit_submission(submission_name);

				dialog.hide();
				onCreated && onCreated(submittal_name, { needsReviewers: false });
			} catch (e) {
				if (submittal_name) {
					dialog.hide();
					onCreated && onCreated(submittal_name, { needsReviewers: true });
					frappe.msgprint({
						title: __("Started, But Incomplete"),
						message: __(
							"{0} was created, but this step failed: {1} Finish configuring it — documents, reviewers — on its own page.",
							[frappe.utils.escape_html(submittal_name), e.message]
						),
						indicator: "orange",
					});
				} else {
					dialog.enable_primary_action();
					frappe.msgprint({
						title: existingSubmittal ? __("Could Not Start Submission") : __("Could Not Create Submittal"),
						message: e.message,
						indicator: "red",
					});
				}
			}
		},
	});
	// discipline/submittal_type may already be defaulted above — onchange never fires for a
	// default, so fire the same suggestion once, immediately, before the dialog is shown.
	if (!existingSubmittal) suggest_submittal_number(dialog, project);
	dialog.show();
}

async function suggest_submittal_number(dialog, project) {
	const discipline = dialog.get_value("discipline");
	const submittal_type = dialog.get_value("submittal_type");
	if (!discipline || !submittal_type) return;
	const suggestion = await suggest_submittal_code(project, discipline, submittal_type).catch(() => "");
	apply_suggested_code(dialog, "submittal_number", suggestion);
}
