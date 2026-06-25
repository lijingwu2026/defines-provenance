#!/usr/bin/env python3
# Reference TRIGGER hook for defines-provenance (Claude Code PostToolUse shape).
#
# Closes the completion cycle automatically: on Edit/Write of a .md file that
# DEFINES a concept (i.e. a SOURCE), it runs the checker's reverse lookup and
# hands your agent the list of DERIVED files to re-read — so a SOURCE change
# never silently leaves its dependents behind.
#
# This is a REFERENCE, not a turnkey product file. It is deliberately generic:
# no project paths, no scope tuples, no extra dependencies. Adapt it to your
# runtime (see README.md in this folder for git pre-commit / CI / Codex). It
# fail-opens on every error — it never blocks an edit.
# Companion: defines_tag_nudge_hook.py covers the CREATE-moment (a new file in a tagged area).
#
# Verify it in your env: `python3 defines_trigger_hook.py --self-test` (hermetic — builds a throwaway
# repo with a multi-concept SOURCE + scoped/unscoped dependents, runs the hook, asserts the grouped
# derived list). Exit 0 = pass. Needs the product checker at ../../defines_provenance.py.
import json
import os
import subprocess
import sys


def main():
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") not in ("Edit", "Write"):
            sys.exit(0)
        fp = (data.get("tool_input") or {}).get("file_path") or ""
    except Exception:
        sys.exit(0)  # fail-open: bad / empty / malformed-shape payload
    if not fp.endswith(".md"):
        sys.exit(0)

    # Resolve the repo root the same way the product scripts do.
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

    # Only act when the edited file is itself a SOURCE (declares DEFINES).
    try:
        with open(fp, errors="ignore") as fh:
            head = "".join(fh.readlines()[:60])
        if "<!-- DEFINES:" not in head:
            sys.exit(0)
        rel = os.path.relpath(fp, root)
    except Exception:
        sys.exit(0)  # fail-open: unreadable file / cross-drive relpath / etc.
    # Point this at wherever you vendored defines_provenance.py.
    checker = os.environ.get("DEFINES_CHECKER", os.path.join(root, "defines_provenance.py"))
    try:
        out = subprocess.run(
            [sys.executable, checker, "--dependents", rel],
            cwd=root, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        sys.exit(0)  # fail-open: never block an edit on a tooling hiccup

    # Relay the checker's output. It is FLAT when nothing is scoped (identical to before), and
    # GROUPED once a `#concept` is in play — `── unscoped … ──` / `── concept: X ──` headers (never
    # `#`-prefixed, so the summary-line filter below keeps them). We never infer WHICH concept you
    # changed: all groups are surfaced, you pick. Group headers render as labels, paths as bullets.
    lines = [ln for ln in out.splitlines() if ln and not ln.startswith("#")]
    files = [ln for ln in lines if not ln.startswith("──")]
    if files:
        print(f"\n[defines-trigger] You changed SOURCE {rel}. Re-check its DERIVED files:",
              file=sys.stderr)
        for ln in lines:
            if ln.startswith("──"):
                print(f"  {ln}", file=sys.stderr)        # concept group header (unscoped / per-concept)
            else:
                print(f"    - {ln}", file=sys.stderr)     # a derived file
        print("  (changed one concept? add `--concept <name>` to narrow; then "
              "`defines_provenance.py --check` before commit to prove no link dangles)",
              file=sys.stderr)
    sys.exit(0)


def self_test():
    """Hermetic: build a throwaway repo with a multi-concept SOURCE + scoped/unscoped dependents, run
    THIS hook as a subprocess on a SOURCE-edit payload, and assert it surfaces the checker's grouped
    derived list (and stays silent on a non-SOURCE edit). Exit 0 = pass."""
    import tempfile
    fails = []

    def chk(name, cond):
        print(f"  {'✅' if cond else '❌'} {name}")
        if not cond:
            fails.append(name)

    checker = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                             "..", "..", "defines_provenance.py"))
    chk("0 product checker present at ../../defines_provenance.py", os.path.exists(checker))
    if not os.path.exists(checker):
        print("\n❌ FAIL: checker not found — run from the repo so ../../defines_provenance.py resolves")
        return 1

    self_path = os.path.abspath(__file__)
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "rules"))
        with open(os.path.join(d, "rules", "auth.md"), "w") as fh:
            fh.write("<!-- DEFINES: session-rules, token-policy -->\n# auth\n")
        with open(os.path.join(d, "login.md"), "w") as fh:                 # scoped dependent
            fh.write("<!-- DEPENDS_ON: rules/auth.md#session-rules -->\n# login\n")
        with open(os.path.join(d, "audit.md"), "w") as fh:                 # unscoped dependent
            fh.write("<!-- DEPENDS_ON: rules/auth.md -->\n# audit\n")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=d, DEFINES_CHECKER=checker)
        src_payload = json.dumps({"tool_name": "Edit",
                                  "tool_input": {"file_path": os.path.join(d, "rules", "auth.md")}})
        dep_payload = json.dumps({"tool_name": "Edit",
                                  "tool_input": {"file_path": os.path.join(d, "login.md")}})
        r_src = subprocess.run([sys.executable, self_path], input=src_payload, env=env,
                               capture_output=True, text=True, timeout=15)
        r_dep = subprocess.run([sys.executable, self_path], input=dep_payload, env=env,
                               capture_output=True, text=True, timeout=15)

    e = r_src.stderr
    chk("1 fires on a SOURCE edit, names the SOURCE", "You changed SOURCE" in e and "rules/auth.md" in e)
    chk("2 groups by concept (── concept: session-rules ── header)", "── concept: session-rules ──" in e)
    chk("3 surfaces the unscoped always-recheck group", "── unscoped" in e and "audit.md" in e)
    chk("4 lists the scoped derived file (login.md)", "login.md" in e)
    chk("5 fail-open exit 0 on the SOURCE edit", r_src.returncode == 0)
    chk("6 silent on a non-SOURCE (DEPENDS-only) edit",
        "You changed SOURCE" not in r_dep.stderr and r_dep.returncode == 0)

    print(f"\n{'✅ self-test PASS' if not fails else '❌ FAIL: ' + ', '.join(fails)}")
    return 0 if not fails else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    main()
