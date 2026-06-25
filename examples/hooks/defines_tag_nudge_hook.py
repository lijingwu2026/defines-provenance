#!/usr/bin/env python3
# Reference TAG-NUDGE hook for defines-provenance (Claude Code PostToolUse shape).
#
# Companion to defines_trigger_hook.py. That hook automates PROPAGATE (a SOURCE
# changed -> re-check its DERIVED). This one covers the other half of upkeep:
# when you CREATE a new .md inside an area you have already been tagging, it nudges
# you to declare its provenance -- so new files do not silently escape the convention.
#
# It NEVER tags for you (declare-don't-infer). It only reminds, and only inside your
# existing provenance zones, so it does not nag every new README / scratch note.
#
# Scope (zero-config by default): a new file is "in scope" if its own directory
# already contains another .md that DEFINES a concept -- i.e. you have already
# established provenance there. Override with DEFINES_SCOPE=rules/,specs/ to set
# explicit path prefixes instead.
#
# Tagging new files is a MUST (the create-moment of upkeep); THIS HOOK is just one way to
# deliver the reminder — the propagate hook works without it. Fail-opens on every error --
# it never blocks an edit.
#
# Usage:
#   (registered as a PostToolUse hook) reads a tool-call JSON on stdin
#   python3 defines_tag_nudge_hook.py --self-test   # hermetic unit test (exit 0 = pass)
import json
import os
import subprocess
import sys

HEADER_LINES = 60


def has_marker(path):
    """True if the file declares either marker in its header."""
    try:
        with open(path, errors="ignore") as fh:
            head = "".join(fh.readlines()[:HEADER_LINES])
    except Exception:
        return False
    return ("<!-- DEFINES:" in head) or ("<!-- DEPENDS_ON:" in head)


def dir_has_defines(dirpath, exclude_abs):
    """True if any .md in dirpath (other than the new file) DEFINES a concept."""
    try:
        names = os.listdir(dirpath)
    except Exception:
        return False
    for name in names:
        if not name.endswith(".md"):
            continue
        p = os.path.join(dirpath, name)
        if os.path.abspath(p) == exclude_abs:
            continue
        try:
            with open(p, errors="ignore") as fh:
                head = "".join(fh.readlines()[:HEADER_LINES])
        except Exception:
            continue
        if "<!-- DEFINES:" in head:
            return True
    return False


def is_new_file(rel, root):
    """True if rel is not yet tracked by git (a freshly created file)."""
    try:
        r = subprocess.run(
            ["git", "ls-files", "--error-unmatch", rel],
            cwd=root, capture_output=True, text=True, timeout=5,
        )
        return r.returncode != 0
    except Exception:
        return False  # fail-silent: can't tell if new -> skip the nudge (never a false nudge)


def _norm_scope_prefix(p):
    """Normalize a DEFINES_SCOPE entry: strip a leading './' and any leading '/', but PRESERVE a
    leading dot in a real dot-directory ('.claude/' stays '.claude/'). The old `lstrip("./")` stripped
    the dot as a char too, so DEFINES_SCOPE='.claude/' became 'claude/' and never matched '.claude/...'."""
    p = p.strip()
    if p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def should_nudge(fp_abs, root, scope_env):
    """The whole decision, factored out so --self-test can exercise it directly.
    Returns True iff this edit should print a tag-nudge."""
    if not fp_abs.endswith(".md"):
        return False
    if has_marker(fp_abs):
        return False  # already declared -- nothing to nudge
    try:
        rel = os.path.relpath(fp_abs, root)
    except Exception:
        return False
    if not is_new_file(rel, root):
        return False  # only nudge genuinely new files
    scope = (scope_env or "").strip()
    if scope:  # explicit override (comma-separated path prefixes)
        prefixes = tuple(p for p in (_norm_scope_prefix(s) for s in scope.split(",")) if p)
        return bool(prefixes) and rel.startswith(prefixes)
    # auto-scope: nudge only inside a dir you have already been tagging
    return dir_has_defines(os.path.dirname(fp_abs), fp_abs)


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") not in ("Edit", "Write"):
            sys.exit(0)
        fp = (data.get("tool_input") or {}).get("file_path") or ""
    except Exception:
        sys.exit(0)
    if not fp.endswith(".md"):
        sys.exit(0)

    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    fp_abs = os.path.abspath(fp)

    if should_nudge(fp_abs, root, os.environ.get("DEFINES_SCOPE", "")):
        rel = os.path.relpath(fp_abs, root)
        print(f"\n[defines-tag] New file {rel} sits in a provenance-tagged area but declares no",
              file=sys.stderr)
        print("  <!-- DEFINES: --> / <!-- DEPENDS_ON: -->. If it owns a concept or derives from one,",
              file=sys.stderr)
        print("  tag it (see CONVENTION.md). If it is neither, ignore this.", file=sys.stderr)
    sys.exit(0)


def _self_test():
    """Hermetic: builds a throwaway git repo in a temp dir, exercises should_nudge()
    over the 6 boundary cases. No dependency on the author's corpus. exit 0 = pass."""
    import shutil
    import tempfile

    def _git(args, cwd):
        subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True, check=True)

    tmp = tempfile.mkdtemp(prefix="defines-tag-selftest-")
    try:
        os.makedirs(os.path.join(tmp, "rules"))
        os.makedirs(os.path.join(tmp, "notes"))
        os.makedirs(os.path.join(tmp, ".claude"))   # dot-dir for the DEFINES_SCOPE='.claude/' (N3) case
        _git(["init", "-q"], tmp)
        _git(["config", "user.email", "t@t.t"], tmp)
        _git(["config", "user.name", "t"], tmp)

        def w(rel, content):
            p = os.path.join(tmp, rel)
            with open(p, "w") as fh:
                fh.write(content)
            return os.path.abspath(p)

        zone = w("rules/auth.md", "<!-- DEFINES: auth -->\n# Auth\n")
        _git(["add", "rules/auth.md"], tmp)                 # tracked + DEFINES = the zone
        new_in_zone = w("rules/new-rule.md", "# New rule\n")   # untracked, untagged, dir has DEFINES
        new_no_zone = w("notes/scratch.md", "# Scratch\n")     # untracked, untagged, dir has no DEFINES
        new_tagged = w("rules/tagged.md", "<!-- DEFINES: t -->\n# T\n")  # untracked but already tagged
        new_dotdir = w(".claude/agent.md", "# agent\n")        # untracked, untagged, in a dot-dir

        cases = [
            ("new untracked untagged in DEFINES-zone", new_in_zone, "", True),
            ("new untracked untagged in no-DEFINES dir", new_no_zone, "", False),
            ("new file with a marker", new_tagged, "", False),
            ("tracked file", zone, "", False),
            ("DEFINES_SCOPE=specs/ on a rules/ file (no match)", new_in_zone, "specs/", False),
            ("DEFINES_SCOPE=rules/ on a rules/ file (match)", new_in_zone, "rules/", True),
            ("DEFINES_SCOPE=.claude/ on a .claude/ file (dot-dir match, N3 regression)",
             new_dotdir, ".claude/", True),
        ]
        failures = []
        for name, fp_abs, scope, want in cases:
            got = should_nudge(fp_abs, tmp, scope)
            if got != want:
                failures.append(f"  - {name}: want {want}, got {got}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures:
        print("defines_tag_nudge_hook --self-test: FAIL")
        print("\n".join(failures))
        return 1
    print(f"defines_tag_nudge_hook --self-test: PASS ({len(cases)} cases)")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    main()
