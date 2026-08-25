import frappe
from frappe.utils import today

frappe.set_user("Administrator")
company = frappe.db.get_value("Company", {}, "name")
PJ = "_VERIFY EGC Scenario"
if frappe.db.exists("Project", {"project_name": PJ}):
	name = frappe.db.get_value("Project", {"project_name": PJ}, "name")
else:
	name = frappe.get_doc({"doctype": "Project", "project_name": PJ, "company": company}).insert().name
project = name

def mkfile(label):
	f = frappe.get_doc({"doctype": "File", "file_name": f"{label}.txt", "is_private": 1,
		"content": f"PDF-{label}"}).insert(ignore_permissions=True)
	return f.file_url

# --- Scenario 4: Drawing revision control -------------------------------------
doc = frappe.get_doc({"doctype": "EGC Project Document", "project": project,
	"document_number": "M-HVAC-SD-0042", "title": "MRI Department HVAC Shop Drawing",
	"document_type": "Drawing", "discipline": "MECH"}).insert()

r00 = frappe.get_doc({"doctype": "EGC Project Document Revision", "document": doc.name,
	"revision": "00", "file": mkfile("rev00"), "revision_date": today()}).insert()
r00.submit()
doc.reload()
print("A. after Rev00 issued      :", doc.current_revision_label, "|", doc.document_status, "|", doc.approval_status)
r00_file_at_issue = frappe.db.get_value("EGC Project Document Revision", r00.name, "file")

# --- Scenario 5: Submittal Rev 00 -> Revise & Resubmit ------------------------
sub = frappe.get_doc({"doctype": "EGC Submittal", "project": project,
	"submittal_number": "SUB-MECH-0027", "title": "HVAC Shop Drawings - MRI Department",
	"submittal_type": "Shop Drawing", "discipline": "MECH"}).insert()
s00 = frappe.get_doc({"doctype": "EGC Submittal Revision", "submittal": sub.name,
	"revision_label": "00", "date_submitted": today(),
	"documents": [{"document_revision": r00.name}]}).insert()
s00.submit()
from egc_projects.egc_projects import submittal_control as sc
sc.record_response(s00.name, "Revise & Resubmit", "Coordinate with ceiling void.")
doc.reload()
print("B. after S00 R&R           :", doc.current_revision_label, "|", doc.approval_status, "(expect Revise & Resubmit)")

# --- Rev 01 issued but NOT yet submitted: must NOT inherit Rev 00's response ---
r01 = frappe.get_doc({"doctype": "EGC Project Document Revision", "document": doc.name,
	"revision": "01", "file": mkfile("rev01"), "revision_date": today()}).insert()
r01.submit()
doc.reload(); r00.reload()
print("C. after Rev01 issued      :", doc.current_revision_label, "|", doc.approval_status,
      "(expect 01 | Not Submitted -- NOT 'Revise & Resubmit')")
print("   Rev00 status            :", r00.revision_status, "| superseded_by:", r00.superseded_by)
print("   Rev00 file preserved    :", frappe.db.get_value("EGC Project Document Revision", r00.name, "file") == r00_file_at_issue)

# --- Submittal Rev 01 -> Approved --------------------------------------------
s01_name = sc.create_next_revision(sub.name)
s01 = frappe.get_doc("EGC Submittal Revision", s01_name)
s01.append("documents", {"document_revision": r01.name})
s01.date_submitted = today()
s01.save(); s01.submit()
doc.reload()
print("D. after S01 submitted     :", doc.approval_status, "(expect Under Review)")
sc.record_response(s01.name, "Approved", "No comments.")
doc.reload(); sub.reload(); s00.reload()
print("E. after S01 Approved      :", doc.approval_status, "| submittal:", sub.submittal_status)
print("   S00 response UNCHANGED  :", s00.response, "|", s00.response_date, "|", s00.submission_status)
print("   both cycles visible     :", [ (r.revision_label, r.submission_status, r.response)
      for r in frappe.get_all("EGC Submittal Revision", filters={"submittal": sub.name},
      fields=["revision_label","submission_status","response"], order_by="submission_seq") ])

# --- history integrity: try to rewrite Rev00's file ---------------------------
try:
	frappe.db.rollback  # noop
	bad = frappe.get_doc("EGC Project Document Revision", r00.name)
	bad.file = mkfile("tampered")
	bad.save()
	print("F. REWRITE ISSUED FILE     : *** NOT BLOCKED -- INTEGRITY FAILURE ***")
except Exception as e:
	print("F. rewrite issued file     : blocked ->", type(e).__name__)

frappe.db.rollback()
print("\n(rolled back - no data left behind)")

# Run with:
#   docker exec -w /workspace/development/frappe-bench frappe_docker_devcontainer-frappe-1 \
#     bash -lc 'bench --site dev.localhost console < apps/egc_projects/scripts/verify_acceptance.py'
#
# Walks acceptance scenarios 4 and 5 end to end against a real site and rolls back afterwards.
# The automated equivalents live in egc_projects/tests/; this exists so the revision and
# approval behaviour can be eyeballed on a live site without trusting the test suite alone.
