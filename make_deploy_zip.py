"""Build deploy.zip with POSIX (forward-slash) paths for Azure Linux.

PowerShell's Compress-Archive writes Windows backslash separators, which Linux
treats as literal filename characters (so `api\server.py` is NOT a package).
This builder uses zipfile with forward-slash arcnames and skips __pycache__.
"""
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "deploy.zip")

DIRS = ["agents", "api", "graph", "prompts", "templates", "knowledge"]
FILES = [
    "apply_plans.py", "blob_storage.py", "config.py", "email_accounts.py",
    "gmail_mark.py", "jd_fetch.py", "knowledge_base.py", "main.py",
    "pending_replies.py", "smtp_send.py", "usage_tracker.py",
    "requirements.txt", "startup.sh",
]


def add_file(zf: zipfile.ZipFile, abs_path: str, arc: str) -> None:
    # Force forward slashes in the archive name.
    zf.write(abs_path, arc.replace(os.sep, "/"))


count = 0
if os.path.exists(OUT):
    os.remove(OUT)

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for d in DIRS:
        d_abs = os.path.join(ROOT, d)
        if not os.path.isdir(d_abs):
            continue
        for cur, dirnames, filenames in os.walk(d_abs):
            dirnames[:] = [x for x in dirnames if x != "__pycache__"]
            for fn in filenames:
                if fn.endswith((".pyc", ".pyo")):
                    continue
                abs_path = os.path.join(cur, fn)
                arc = os.path.relpath(abs_path, ROOT)
                add_file(zf, abs_path, arc)
                count += 1
    for f in FILES:
        f_abs = os.path.join(ROOT, f)
        if os.path.isfile(f_abs):
            add_file(zf, f_abs, f)
            count += 1

print(f"Wrote {OUT} with {count} files")
# Sanity: confirm api/server.py present with forward slash and no backslashes.
with zipfile.ZipFile(OUT) as zf:
    names = zf.namelist()
    assert "api/server.py" in names, "api/server.py missing!"
    bad = [n for n in names if "\\" in n]
    assert not bad, f"backslash entries: {bad[:3]}"
    print("OK: api/server.py present; all paths use forward slashes")
