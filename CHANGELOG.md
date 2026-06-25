<!-- DEPENDS_ON: defines_provenance.py -->

# Changelog

All notable changes are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/) (0.y.z
— pre-1.0, anything may change).

The bundled script `defines_provenance.py` (checker) carries its own `__version__` = **0.3.0**;
the heading below is the **artifact release** version. The two `examples/hooks/` reference hooks
(`defines_trigger_hook.py`, `defines_tag_nudge_hook.py`) are **unversioned reference files** —
copy-and-adapt examples, not independently-released components.

## [0.3.0] — concept-scoped DEPENDS_ON (opt-in)

### Added
- **`defines_provenance.py` (0.2.2 → 0.3.0) — opt-in concept-scoped `DEPENDS_ON`.** An edge MAY suffix
  `#concept` (a slug the target's `DEFINES` declares) to scope a dependency to one concept —
  `rules/base-policy.md#session-rules`. A bare `path` is whole-file and stays the always-flagged
  **default**; unscoped behaviour is byte-identical to 0.2.x, so this is fully backward-compatible. New
  `--dependents <src> --concept X` narrows the reverse lookup to *that concept ∪ unscoped* edges; the
  output stays flat until a scoped edge exists, then groups (`unscoped · always re-check` + per-concept).
  **Conservative by design:** a `#concept` the target doesn't DEFINE is treated as **unscoped** (fail-safe
  — never silently dropped), and `--check` surfaces it as a **🟡 advisory — non-blocking, explicitly NOT a
  🔴 hard-fail.** The reference `examples/hooks/defines_trigger_hook.py` groups its re-check list by concept
  to match. The checker still does **not** judge whether a `#concept` is the *right* one — mis-attribution
  stays a human call (see README "Honest limits"). Self-test 15 → 27 (adds parse / `--concept`
  filter-exclude / fail-safe / 🟡-advisory negative cases).
- **Security hardening (pre-publication review).** Bounded the `CONTIG_TOK` candidate scan in
  `extract_candidates` to the first 512 chars of a value: a long no-extension `DEPENDS_ON` value could
  otherwise trigger O(n²) regex backtracking (a CI denial-of-service on attacker-controlled markdown).
  Real path values never approach 512 chars, so path extraction is unchanged. Also removed an unused
  `import glob`. Self-test 27 → 28 (adds the ReDoS-guard timing case).
- **`examples/hooks/defines_tag_nudge_hook.py` — new-file TAG-nudge reference hook (the create-moment of upkeep).** Companion
  to `examples/hooks/defines_trigger_hook.py` (the propagate trigger). On `Edit`/`Write` of a *new*
  untagged `.md` inside an already-tagged directory, it prints a one-line stderr reminder to declare the
  file's provenance — so a new file doesn't silently escape the convention. **Auto-scoped** (a file is in
  scope when its own directory already contains a `<!-- DEFINES: -->` sibling; `DEFINES_SCOPE=rules/,specs/`
  overrides). **Nudge-only** — never auto-tags (declare-don't-infer); fail-opens, never blocks an edit.
  One way to wire the create-moment (which is required — the root-file instruction is the other); works independently of the propagate trigger. Reference file (no `__version__`, like the trigger hook).
- **`defines_provenance.py` (0.2.2) — `--dependents <source>` reverse lookup.** Read-only: lists every
  file whose `DEPENDS_ON` marker textually points at `<source>` (normpath match, srcdir-rel ∪ root-rel;
  works even before a rename's target exists — existence-independent). Powers the SOURCE→DERIVED
  **propagation discipline** (change a SOURCE → see who to re-check) now documented in `CONVENTION.md`
  ("Keeping in sync"). It is NOT content-drift detection — it lists who
  references the source, not whether their content went stale (that judgement stays human). Pure read;
  the "checker never writes" invariant holds. Self-test 14 → 15.

### Fixed
- **`defines_provenance.py` 0.2.0 → 0.2.1 — the checker now scans dot-directories.** The scan moved
  from `glob('**/*.md')` (which silently skips `.claude/`, `.cursor/`, `.github/`, `.windsurf/`) to
  `os.walk`, so markers placed inside those dirs — exactly where agent rules live — are now
  validated by `--check` / `--report`. Read-only change; the "checker never writes" invariant holds
  (re-verified by a byte-unchanged test). `DEFINES_EXCLUDE` now matches dir **basenames** (was
  path-substrings). Added a hermetic dot-dir self-test case (13 → 14).

### Notes
- The checker scan stays `.md`-only by design: non-`.md` rule files (`.cursorrules`, `.clinerules`,
  Cursor `.mdc`) remain out of scope (the marker convention is a `.md` header convention).

## [0.2.0] — checker baseline
- `defines_provenance.py` — dependency-free existence checker for `DEFINES` / `DEPENDS_ON` markers:
  `--report` / `--check` / `--baseline` (grandfather + delta-gate) / `--self-test` (13 hermetic
  cases). Frozen.
