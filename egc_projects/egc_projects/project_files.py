# Copyright (c) 2026, EGC and contributors
# For license information, please see license.txt

"""Per-project folder structure in Frappe's native File system (docs/ARCHITECTURE.md) — new
uploads only, no migration of already-uploaded files. A folder `File` row's own `.name` is always
its parent's `.name` + "/" + its own `file_name` (frappe/core/doctype/file/file.py
`get_name_based_on_parent_folder`), so the full path of any project's subfolder is fully
deterministic string interpolation, never a lookup — every caller (Python or JS) can build it
directly as long as `ensure_project_folders()` has actually run for that project first.

See hooks.py's `Project.after_insert` (new projects) and install.py's
`provision_all_project_folders()` (projects that already existed before this feature landed).
"""

import frappe
from frappe.core.api.file import create_new_folder

PROJECT_SUBFOLDERS = ("Documents", "Drawings", "Submittals", "Photos")

_HOME_FOLDER = "Home"
_PROJECTS_ROOT = "Projects"


def project_folder_path(project: str, subfolder: str | None = None) -> str:
	base = f"{_HOME_FOLDER}/{_PROJECTS_ROOT}/{project}"
	return f"{base}/{subfolder}" if subfolder else base


def _ensure_folder(file_name: str, parent_folder: str) -> None:
	full_path = f"{parent_folder}/{file_name}"
	if frappe.db.exists("File", full_path):
		return
	create_new_folder(file_name, parent_folder)


def ensure_project_folders(project: str) -> None:
	"""Idempotent — safe to call on every Project insert AND in a loop over every existing
	Project at install time. A repeat call for an already-provisioned project is just four
	fast `db.exists` reads."""
	if not project:
		return
	_ensure_folder(_PROJECTS_ROOT, _HOME_FOLDER)
	project_root = f"{_HOME_FOLDER}/{_PROJECTS_ROOT}"
	_ensure_folder(project, project_root)
	project_path = project_folder_path(project)
	for subfolder in PROJECT_SUBFOLDERS:
		_ensure_folder(subfolder, project_path)


def provision_project_folders(doc, method=None) -> None:
	"""`Project`'s `after_insert` doc_event — see hooks.py."""
	ensure_project_folders(doc.name)
