#!/usr/bin/env bash
# ship_check.sh — publish precondition for defines-provenance.
#
# Aggregates the machine-checkable ship gates and exits non-zero on ANY failure, so a
# release script / CI can REFUSE to publish when something regresses. This is the
# "validate-skills.js-in-CI" pattern (a structural gate that refuses to ship) applied to
# this repo — it is NOT a feature of the tool; it just runs commands that already exist.
# It is also the build-story's "the checker obeys its own repo" beat (gate [3]).
#
# Usage (from anywhere):  bash ship_check.sh    # exit 0 = safe to publish, 1 = blocked
set -u
cd "$(dirname "$0")" || exit 2

fail=0
ok()  { printf '  ✅ %s\n' "$1"; }
bad() { printf '  ❌ %s\n' "$1"; fail=1; }

echo "ship-check: defines-provenance"
echo

echo "[1/6] required files present (repo-mechanics floor)"
for f in LICENSE README.md CONVENTION.md .gitignore defines_provenance.py examples/hooks/defines_trigger_hook.py examples/hooks/defines_tag_nudge_hook.py; do
  [ -f "$f" ] && ok "$f" || bad "missing $f"
done
if ls examples/*/*.md >/dev/null 2>&1; then ok "examples/ has runnable .md"; else bad "no runnable example under examples/"; fi
echo

echo "[2/6] self-test (hermetic units, FP=0 gate)"
if out=$(python3 defines_provenance.py --self-test 2>&1); then ok "self-test PASS"; else bad "self-test FAILED"; echo "$out"; fi
if out=$(python3 examples/hooks/defines_tag_nudge_hook.py --self-test 2>&1); then ok "tag-nudge self-test PASS"; else bad "tag-nudge self-test FAILED"; echo "$out"; fi
echo

echo "[3/6] self-dogfood (the tool obeys the convention it enforces)"
if DEFINES_ROOT="$(pwd)" DEFINES_EXEMPT=examples python3 defines_provenance.py --check >/dev/null 2>&1; then ok "own docs pass --check"; else bad "the tool does NOT obey its own convention"; fi
echo

echo "[4/6] sanitize — gitleaks (HARD gate, fail-closed)"
if command -v gitleaks >/dev/null 2>&1; then
  if out=$(gitleaks dir . 2>&1); then ok "no leaks"; else bad "gitleaks found leaks"; echo "$out" | tail -5; fi
else
  bad "gitleaks not installed — sanitize is a HARD gate, cannot pass without it (install: https://github.com/gitleaks/gitleaks)"
fi
echo

# Catches author-corpus leak on two mechanizable axes: (1) PATH — absolute home paths a local run can
# leak (/Users/, /home/) (2) IDENTITY — YOUR handle / private dir name / launchd labels, supplied via
# the SHIPCHECK_IDENTITY env var (unset = path axis only):
#   SHIPCHECK_IDENTITY='myname|myvault|com.myname' bash ship_check.sh
# A third axis — config/data OVERFIT to your corpus (author-specific filenames shipped as if generic)
# — is NOT grep-gatable and stays a HUMAN sanitize-review item (see README / CONVENTION).
echo "[5/6] no author-corpus leak (path + identity)"
leak_re="/Users/|/home/${SHIPCHECK_IDENTITY:+|$SHIPCHECK_IDENTITY}"
if hits=$(grep -rnE "$leak_re" --exclude=ship_check.sh --exclude-dir=__pycache__ --exclude-dir=.git . 2>/dev/null); then
  bad "author-corpus leak (path/identity):"; echo "$hits"
else ok "no absolute-path / configured-identity leak"; fi
echo

echo "[6/6] zero unresolved placeholder"
# '<repo>' / '(pending)' are the ONBOARDING setup-prompt placeholders (ST2) — guard so an unfilled
# copy-paste prompt can never ship. -w keeps bare words ('repository', 'pending') from false-matching.
if hits=$(grep -rnwE 'TODO|FIXME|XXX|TKTK|PLACEHOLDER|FILL_ME|REPLACE_ME|your-name-here|<repo>|\(pending\)' --exclude=ship_check.sh --exclude-dir=__pycache__ --exclude-dir=.git . 2>/dev/null); then
  bad "unresolved placeholder(s):"; echo "$hits"
else ok "no unresolved placeholder"; fi
echo

if [ "$fail" -eq 0 ]; then
  echo "ship-check: ✅ ALL GATES PASS — mechanically safe to publish."
  echo "            (The identity/value call — public under your name? — is a separate human decision.)"
  exit 0
else
  echo "ship-check: ❌ BLOCKED — fix the ❌ above before publishing."
  exit 1
fi
