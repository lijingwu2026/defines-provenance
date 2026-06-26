#!/usr/bin/env python3
"""defines_provenance.py — existence checker for DEFINES / DEPENDS_ON provenance markers.

A small, dependency-free script that scans a tree of markdown (and other text) files
for `<!-- DEFINES: X -->` / `<!-- DEPENDS_ON: Y -->` header annotations and verifies
that every path they reference actually exists. It is the deterministic backstop for a
hand-written convention: neither semantic similarity (inferred) nor a backlink web (undirected) is
structural dependency — dependency has to be *declared*, *directional*, and *owned* (which file is the
SOURCE), and once declared it can be *mechanically checked*.

See CONVENTION.md for what the markers mean and README.md for the story behind them.

== Configuration (all optional, via environment) ==
  DEFINES_ROOT      tree to scan (default: $CLAUDE_PROJECT_DIR, else current dir)
  DEFINES_EXCLUDE   comma-separated dir BASENAMES to prune (default: .git,node_modules,.venv,vendor)
                    (0.2.1: basenames, not path-substrings — the scan now os.walk-descends dot-dirs)
  DEFINES_EXEMPT    comma-separated path prefixes whose broken targets are ignored
                    (e.g. changelog/history dirs that reference now-moved files)

== Tokenizer rules (each driven by a real boundary case; see --self-test) ==
  1. Non-ASCII in path: `docs/設計/spec.md` -> char class includes CJK, never truncated
  2. Spaces in path: `My App Spec.md` -> candidate keeps the de-annotated full value (spaces intact)
  3. Path embedded in prose: `runs daily ... state/x.json` -> take the contiguous path token, not the whole sentence
  4. Comma inside an annotation: `config.json (a, b)` -> strip `(...)` BEFORE splitting (inner commas survive)
  5. Ideographic comma separator: `a.md、b.md` -> split set includes `、`
  6. Prose-DEFINES concept name: `scripts/ as a paradigm` -> require a token ending in .ext (auto-excluded)

== Core rule ==
  - resolve-driven: a value is OK if ANY of its candidates resolves
    (candidates = de-annotated full value + each contiguous path segment)
  - split set = `,` `，` `、`; strip `(...)` / `（...）` annotations before splitting
  - bare-name downgrade: a name with no `/` that does not resolve -> 🟡 (ambiguous: concept vs unqualified)
                         a path with `/` that does not resolve            -> 🔴 (confident broken)
  - prose escape: same line carries `<!-- DEFINES-EXEMPT: ... -->`, OR path under a DEFINES_EXEMPT prefix
  - fenced-code escape: markers inside ``` / ~~~ blocks are illustrative (a doc teaching the
    convention), not live provenance -> skipped

== Usage ==
  python3 defines_provenance.py --self-test    # hermetic boundary-case unit tests (FP=0 gate)
  python3 defines_provenance.py --report       # list every broken target (🔴 / 🟡)  ← run this FIRST on a new tree
  python3 defines_provenance.py --check        # exit 0 = clean / 1 = has 🔴
  python3 defines_provenance.py --baseline > .defines.baseline          # snapshot current 🔴 to grandfather them
  python3 defines_provenance.py --check --baseline .defines.baseline    # exit 1 only on NEW 🔴 (delta gate)
  python3 defines_provenance.py --dependents rules/auth.md             # reverse: who DEPENDS_ON this SOURCE? (propagation)
  python3 defines_provenance.py --dependents rules/auth.md --concept session-rules   # scoped: only dependents pinned to ONE concept (propagation fast-path)
  python3 defines_provenance.py --version      # print version

== Concept-scoped DEPENDS_ON (0.3.0) ==
  Scope a focused dependent at creation: a file that derives from just ONE concept the target DEFINES
  suffixes `#concept` — e.g. `<!-- DEPENDS_ON: rules/auth.md#session-rules -->`. A broad consumer keeps a
  bare path (`rules/auth.md`) = whole-file, the always-safe default. `--dependents … --concept X` then narrows propagation to the dependents
  pinned to X (∪ unscoped ∪ a fail-safe: a `#concept` the target does NOT DEFINE is treated as unscoped,
  so a typo is never silently dropped). `--check` adds a 🟡 NON-BLOCKING advisory when a `#concept` is
  not among the target's DEFINES — it never exits 1 on it (scope correctness is a soft signal).

== Adopting on an existing tree (the baseline workflow) ==
  This tool checks that DECLARED markers point at files that exist; it does NOT nag about files
  that have no marker yet. So a fresh tree passes trivially — you opt in by declaring relationships.
  The wall is incremental CI adoption when some refs are *already* broken. The baseline solves it:
    1. `--report`  — see where you stand (nothing fails; this is the day-1 floor).
    2. declare DEFINES/DEPENDS_ON for the relationships you know.
    3. `--baseline > .defines.baseline`  — snapshot any refs that are already broken, commit it.
    4. `--check --baseline .defines.baseline` in CI  — fails ONLY on NEW breakage; the grandfathered
       ones don't block you. Burn the baseline down over time.
  (eslint-suppressions semantics: grandfather current violations, gate deltas — NOT a per-finding
  "I accept this" decision like a secrets baseline.)

This repo dogfoods its own convention: run
  DEFINES_EXEMPT=examples python3 defines_provenance.py --check
from the repo root and it checks its own docs' DEFINES/DEPENDS_ON markers (exempting the
deliberately-broken test fixtures under examples/). The tool obeys the convention it enforces.
"""
import os
import re
import sys

__version__ = "0.3.0"

ROOT = os.environ.get("DEFINES_ROOT") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()

EXT = r"(?:md|py|json|sh|plist|js|ts|ya?ml)"
# Contiguous path segment (no spaces): word chars + CJK + ./~- , ending in a known .ext
CONTIG_TOK = re.compile(r"[\w./一-鿿~-]+\." + EXT + r"\b")
# Does the de-annotated full value end in a known .ext?
ENDS_EXT = re.compile(r"\." + EXT + r"$")
DEFINES_RE = re.compile(r"<!--\s*(DEFINES|DEPENDS_ON):\s*(.+?)\s*-->")
EXEMPT_RE = re.compile(r"<!--\s*DEFINES-EXEMPT")

_DEFAULT_EXCLUDES = ".git,node_modules,.venv,vendor"
# DEFINES_EXCLUDE = dir BASENAMES to prune during the walk. (0.2.1: changed from path-substring
# matching when the scan moved glob → os.walk to descend into dot-directories — see scan().)
EXCLUDE_NAMES = frozenset(
    d.strip() for d in os.environ.get("DEFINES_EXCLUDE", _DEFAULT_EXCLUDES).split(",") if d.strip()
)
# DEFINES / DEPENDS_ON are a HEADER convention (frontmatter -> before the title). A DEFINES
# appearing mid-file is usually a changelog quote or an inline example whose path is relative
# to some other file, not this one -> scanning header-only avoids those false positives.
HEADER_LINES = 60

# Path prefixes whose broken targets are ignored (history/changelog dirs that reference moved files).
EXEMPT_PREFIXES = tuple(p.strip() for p in os.environ.get("DEFINES_EXEMPT", "").split(",") if p.strip())


def strip_annotations(s):
    """Remove each `(...)` / `（...）` annotation segment (including its inner commas).

    Uses a per-occurrence `[（(][^（()）]*[)）]` rather than a greedy `.*$`: the greedy form
    would, on `A (note1), B (note2)`, delete from the first `(` to end of line and swallow the
    second value -> a missed report.
    """
    return re.sub(r"[（(][^（()）]*[)）]", "", s).strip()


def split_values(defines_content):
    """Strip annotations, then split on , ， 、 . Returns a list of values."""
    body = strip_annotations(defines_content)
    return [v.strip() for v in re.split(r"[,，、]", body) if v.strip()]


def extract_candidates(value):
    """Candidates = de-annotated full value (<=4 words, to cover spaced paths but exclude prose)
    + each contiguous path segment (no spaces)."""
    cands = []
    deann = strip_annotations(value).strip("`").strip()
    # Drop trailing prose-note words (Item N / §.. / per .. / L<digit>)
    deann2 = re.sub(r"\s+(Item|§|per|L\d).*$", "", deann).strip()
    for c in (deann, deann2):
        # <=4-word guard: 'My App Spec.md' (3 words) kept; a long prose sentence (>4 words) excluded,
        # left to the contiguous-token path below.
        if ENDS_EXT.search(c) and len(c.split()) <= 4 and c not in cands:
            cands.append(c)
    # ReDoS guard: CONTIG_TOK is O(n²) backtracking on a long no-extension run, so bound the scan.
    # A single post-split DEPENDS_ON/DEFINES value is one path (+ optional #concept / annotation) —
    # never near 512 chars; anything longer is prose we wouldn't extract a path from anyway.
    cands += CONTIG_TOK.findall(value[:512])
    # dedup + drop glob / placeholder tokens
    out = []
    for c in dict.fromkeys(cands):
        if "<" in c or ">" in c or "*" in c:
            continue
        out.append(c)
    return out


# ── concept-scoped DEPENDS_ON grammar (0.3.0) ──────────────────────────────────────
# A DEPENDS_ON value MAY suffix `#concept` to scope to ONE concept the target DEFINES, e.g.
# `rules/auth.md#session-rules`. The suffix is a single DEFINES slug — word chars + `-` only; a `#`
# followed by anything path-like (`notes#1.md`) is NOT a scope, so the whole value stays the path.
CONCEPT_RE = re.compile(r"^[\w-]+$")


def parse_depends_value(value):
    """Split a DEPENDS_ON value into (path, concept). `path#concept` -> (path, concept) ONLY when
    `concept` is a bare DEFINES slug (no `.` / `/`); otherwise the whole value is the path and concept
    is None (so `notes#1.md`, or a `#` inside a real path, is never misread as a scope)."""
    v = value.strip()
    if "#" in v:
        head, tail = v.rsplit("#", 1)
        if head and CONCEPT_RE.match(tail):
            return head.strip(), tail.strip()
    return v, None


def resolve_exists(path, srcdir):
    """~-expand / absolute / relative-to-source normpath / relative-to-root: any hit -> True."""
    p = path.strip().strip("`")
    if not p:
        return True
    if p.startswith("~"):
        return os.path.exists(os.path.expanduser(p))
    if os.path.isabs(p):
        return os.path.exists(p)
    rel_src = os.path.normpath(os.path.join(srcdir, p))
    if os.path.exists(rel_src):
        return True
    return os.path.exists(os.path.join(ROOT, p))


def is_exempt(srcrel, value, line, prefixes=None):
    """Same-line EXEMPT marker OR path under a DEFINES_EXEMPT prefix -> exempt."""
    if EXEMPT_RE.search(line):
        return True
    for prefix in (EXEMPT_PREFIXES if prefixes is None else prefixes):
        # PATH-prefix, not string-prefix: `DEFINES_EXEMPT=examples` exempts `examples/x.md` but NOT
        # `examples-old/x.md`. Match an exact path or a trailing-slash directory boundary.
        stem = prefix.rstrip("/")
        if srcrel == stem or srcrel.startswith(stem + "/"):
            return True
    return False


def classify(value, srcdir):
    """Return None (ok / no path) or (severity, repr_path). severity in {'🔴','🟡'}."""
    cands = extract_candidates(value)
    if not cands:
        return None  # prose-DEFINES concept name (no .ext token) -> not checked
    if any(resolve_exists(c, srcdir) for c in cands):
        return None  # any candidate resolves -> OK
    # none resolve: bare-name (no /) -> 🟡 ; contains a dir -> 🔴
    repr_path = cands[0]
    has_dir = any("/" in c for c in cands)
    return ("🔴" if has_dir else "🟡", repr_path)


def _resolve_to_file(path, srcdir, root=None):
    """Resolved filesystem path of `path` (relative-to-source ∪ relative-to-root ∪ abs/~), or None.
    Mirrors resolve_exists() so concept-validation reads the same file the checker resolves."""
    root = root or ROOT
    p = path.strip().strip("`")
    if not p:
        return None
    if p.startswith("~"):
        ep = os.path.expanduser(p)
        return ep if os.path.exists(ep) else None
    if os.path.isabs(p):
        return p if os.path.exists(p) else None
    rel_src = os.path.normpath(os.path.join(srcdir, p))
    if os.path.exists(rel_src):
        return rel_src
    rel_root = os.path.join(root, p)
    return rel_root if os.path.exists(rel_root) else None


def _read_defines_set(resolved_path, cache):
    """Union of DEFINES slugs declared across the header of the file at `resolved_path`.
    A target may split its concepts over MULTIPLE DEFINES lines (S8: union, not first-line-only).
    Cached per scan by resolved path (S9: one read per target, not per dependent edge)."""
    if resolved_path in cache:
        return cache[resolved_path]
    slugs = set()
    try:
        with open(resolved_path, errors="ignore") as fh:
            header = fh.readlines()[:HEADER_LINES]
    except OSError:
        cache[resolved_path] = slugs
        return slugs
    in_fence = False
    for ln in header:
        if ln.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for m in DEFINES_RE.finditer(ln):
            if m.group(1) == "DEFINES":
                for v in split_values(m.group(2)):
                    slugs.add(v.strip())
    cache[resolved_path] = slugs
    return slugs


def validate_concept_scope(value, srcdir, root=None, cache=None):
    """A DEPENDS_ON value with a `#concept` scope -> 🟡 (advisory, NON-BLOCKING) when the target
    resolves but does NOT DEFINE that concept (likely a typo / stale rename). Returns None when the
    value is unscoped, the target can't be resolved (the broken-path check already owns that), or the
    concept is valid. NEVER 🔴 — a scope mismatch is soft; the fail-safe treats it as unscoped."""
    path, concept = parse_depends_value(value)
    if concept is None:
        return None
    if cache is None:
        cache = {}
    target = _resolve_to_file(path, srcdir, root)
    if target is None:
        return None  # unresolved path -> classify() already flags it; don't double-report
    if concept in _read_defines_set(target, cache):
        return None
    return ("🟡", f"{path}#{concept} (concept not in target's DEFINES)")


def _iter_md(root):
    """Yield every .md file under root, DESCENDING INTO dot-directories (.claude/.cursor/.github/
    .windsurf — where agent rules live), pruning excluded dir basenames. Replaces glob('**/*.md'),
    which silently skips dotfiles/dirs and so never validated markers inside them (fixed 0.2.1)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_NAMES]
        for fn in filenames:
            if fn.endswith(".md"):
                yield os.path.join(dirpath, fn)


def scan(root=None):
    """Scan the tree, return [(srcrel, typ, severity, path), ...]."""
    root = root or ROOT
    broken = []
    defines_cache = {}  # resolved-abspath -> DEFINES slug set (S9: one read per target across the scan)
    for f in _iter_md(root):
        try:
            with open(f, errors="ignore") as fh:
                header = fh.readlines()[:HEADER_LINES]  # header-only (DEFINES is a header convention)
        except OSError:
            continue
        srcdir = os.path.dirname(f)
        srcrel = os.path.relpath(f, root)
        in_fence = False
        for ln in header:
            # Skip fenced code blocks: a doc that *teaches* the convention shows marker
            # examples inside ``` / ~~~ fences; those are illustrative, not live provenance.
            if ln.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for m in DEFINES_RE.finditer(ln):
                typ = m.group(1)
                for val in split_values(m.group(2)):
                    if is_exempt(srcrel, val, ln):
                        continue
                    r = classify(val, srcdir)
                    if r:
                        broken.append((srcrel, typ, r[0], r[1]))
                    elif typ == "DEPENDS_ON":
                        # path resolved OK — additionally check a #concept scope (0.3.0, advisory 🟡)
                        a = validate_concept_scope(val, srcdir, root, defines_cache)
                        if a:
                            broken.append((srcrel, typ, a[0], a[1]))
    return sorted(set(broken))


# ───────────────────────── --dependents (reverse lookup: who DEPENDS_ON a source — propagation) ─────────────────────────
# The forward check answers "do my declared links resolve?"; the reverse answers "if I change THIS
# source, which files DEPEND on it and might now be stale?". That who-to-check list is what makes the
# SOURCE→DERIVED propagation discipline cheap. This is a READ-ONLY textual match, NOT content-drift
# detection: it tells you who references the source, not whether their content went stale (no
# deterministic tool can — that judgement stays human; see CONVENTION.md "Keeping in sync").
def _candidate_targets(value, srcrel_dir):
    """Textual normpath targets a DEPENDS_ON value could point at: relative to the depending file's
    dir (srcrel_dir) ∪ relative to the scan root. Reuses the checker's own tokenizer
    (extract_candidates). Unlike resolve_exists(), this does NOT require the target to exist — a
    reverse lookup must still find dependents mid-rename, before the new path is created."""
    targets = set()
    for cand in extract_candidates(value):
        c = cand.strip().strip("`")
        if not c or c.startswith("~") or os.path.isabs(c):
            continue  # reverse lookup is tree-relative only
        targets.add(os.path.normpath(os.path.join(srcrel_dir, c)))  # relative to the depending file
        targets.add(os.path.normpath(c))                            # relative to root
    return targets


def _find_dependent_edges(source, root=None):
    """Core reverse scan: list of (srcrel, edge_concept) for every DEPENDS_ON edge whose PATH
    textually points at `source`. edge_concept = the `#concept` scope, or None (unscoped/whole-file).
    READ-ONLY. Mirrors scan()'s header-only / fenced-skip / os.walk traversal; textual normpath match
    (srcdir-rel ∪ root-rel); existence-independent (finds dependents mid-rename)."""
    root = root or ROOT
    want = os.path.normpath(source.strip().strip("`"))
    edges = []
    for f in _iter_md(root):
        try:
            with open(f, errors="ignore") as fh:
                header = fh.readlines()[:HEADER_LINES]
        except OSError:
            continue
        srcrel = os.path.relpath(f, root)
        srcrel_dir = os.path.dirname(srcrel)
        in_fence = False
        for ln in header:
            if ln.lstrip().startswith(("```", "~~~")):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for m in DEFINES_RE.finditer(ln):
                if m.group(1) != "DEPENDS_ON":
                    continue
                for val in split_values(m.group(2)):
                    path, concept = parse_depends_value(val)
                    if want in _candidate_targets(path, srcrel_dir):
                        edges.append((srcrel, concept))
    return edges


def _read_defines_set_for_source(source, root=None):
    """DEFINES slug set of the `source` file itself (to validate edge scopes during reverse lookup).
    Empty set when the source can't be read (mid-rename) -> the fail-safe then keeps every scoped edge."""
    root = root or ROOT
    s = source.strip().strip("`")
    candidate = s if os.path.isabs(s) else os.path.join(root, s)
    return _read_defines_set(candidate, {}) if os.path.exists(candidate) else set()


def find_dependents(source, concept=None, root=None):
    """Reverse lookup: sorted unique files whose DEPENDS_ON points at `source`. With `concept`, keep an
    edge iff it is unscoped (None), scoped to exactly `concept`, OR its scope is NOT a real DEFINES of
    `source` (FAIL-SAFE: a typo'd / invalid scope is treated as unscoped, never silently dropped — a
    propagation pass can't miss a mis-tagged dependent). Existence-independent."""
    edges = _find_dependent_edges(source, root)
    if concept is None:
        return sorted({srcrel for srcrel, _ in edges})
    src_defines = _read_defines_set_for_source(source, root)
    keep = set()
    for srcrel, ec in edges:
        if ec is None or ec == concept or ec not in src_defines:
            keep.add(srcrel)
    return sorted(keep)


def dependents_by_concept(source, root=None):
    """Group reverse-lookup hits for surfacing. Returns (unscoped, groups):
      unscoped = sorted srcrel of whole-file (always-relevant) dependents;
      groups   = {concept-key: sorted srcrel} for scoped dependents, sorted by key. A scope that is
                 NOT a DEFINES of `source` is grouped under '<scope> ⚠unrecognized' so a typo stays
                 visible rather than hidden (matches the reverse fail-safe)."""
    edges = _find_dependent_edges(source, root)
    src_defines = _read_defines_set_for_source(source, root)
    unscoped, groups = set(), {}
    for srcrel, ec in edges:
        if ec is None:
            unscoped.add(srcrel)
        else:
            key = ec if (not src_defines or ec in src_defines) else f"{ec} ⚠unrecognized"
            groups.setdefault(key, set()).add(srcrel)
    return sorted(unscoped), {k: sorted(v) for k, v in sorted(groups.items())}


# ───────────────────────── baseline (grandfather current 🔴, gate deltas — eslint-suppressions semantics) ─────────────────────────
# Onboarding mechanic: a stranger adopting CI on an existing tree may have refs that are *already*
# broken (a DEPENDS_ON to a since-moved file). Forcing them to fix all of it before turning on
# --check is the adoption wall. A baseline snapshots the current 🔴 set; --check --baseline then
# fails only on NEW 🔴. Plain text (one tab-separated row per finding) — no JSON schema to version,
# because we store path identities, not labeled metadata (unlike a secrets baseline).
_BASELINE_HEADER = "# defines-provenance baseline — grandfathered broken refs (regenerate with --baseline)"


def _key(finding):
    """Stable identity of a broken finding for baseline matching: (source, marker-type, target)."""
    srcrel, typ, sev, path = finding
    return (srcrel, typ, path)


def write_baseline(root=None):
    """Print a plain-text baseline of the currently-broken (🔴) targets to stdout."""
    red = [b for b in scan(root) if b[2] == "🔴"]
    print(_BASELINE_HEADER)
    print(f"# {len(red)} entry(ies); format: <source>\\t<DEFINES|DEPENDS_ON>\\t<target>")
    for srcrel, typ, sev, path in red:
        print(f"{srcrel}\t{typ}\t{path}")
    return 0


def load_baseline(path):
    """Parse a baseline file into a set of (source, type, target) keys. Missing file -> empty set."""
    keys = set()
    try:
        with open(path, errors="ignore") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return keys
    for ln in lines:
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        parts = ln.split("\t")
        if len(parts) == 3:
            keys.add((parts[0], parts[1], parts[2]))
    return keys


# ───────────────────────── self-test (hermetic: builds its own fixtures, FP=0 gate) ─────────────────────────
def self_test():
    import tempfile

    fails = []

    def chk(name, cond):
        print(f"  {'✅' if cond else '❌'} {name}")
        if not cond:
            fails.append(name)

    # case 1 non-ASCII path: CJK segment not truncated
    c1 = extract_candidates("docs/設計資料/spec.md")
    chk("1 non-ASCII path not truncated", any("設計資料" in c for c in c1))

    # case 2 spaced path: de-annotated full value preserved
    c2 = extract_candidates("My App Spec.md")
    chk("2 spaced path preserved", "My App Spec.md" in c2)

    # case 3 path embedded in prose: take the contiguous token, not the sentence
    c3 = extract_candidates("runs daily at 07:00 writing state/x.json")
    chk("3 prose-embedded path -> token", "state/x.json" in c3 and not any(" " in c and "runs" in c for c in c3))

    # case 4 comma inside an annotation: not chopped by the inner comma
    v4 = split_values("config/settings.json (source of hooks, sync on change)")
    chk("4 comma in annotation not chopped", v4 == ["config/settings.json"])

    # case 5 ideographic comma: split into two values
    v5 = split_values("a/x.md、b/y.md")
    chk("5 ideographic-comma split", v5 == ["a/x.md", "b/y.md"])

    # case 6 bare-name downgrade + dir -> 🔴 (use a hermetic empty tree so nothing resolves)
    with tempfile.TemporaryDirectory() as empty:
        r6a = classify("nonexistent_xyz_zzz.md", empty)
        r6b = classify("nonexistent_dir_zzz/file.md", empty)
    chk("6a bare-name -> 🟡", r6a is not None and r6a[0] == "🟡")
    chk("6b contains dir -> 🔴", r6b is not None and r6b[0] == "🔴")

    # case 7 prose concept name (no .ext) -> skipped
    chk("7 prose concept name skipped", classify("scripts/ as a paradigm", ROOT) is None)

    # case 8 a real existing path resolves OK (hermetic: create the file we test against)
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "EXISTS.md"), "w").close()
        chk("8 real path resolves OK", classify("EXISTS.md", d) is None)

    # case 9 fenced code block: an illustrative marker inside ``` is NOT scanned as live,
    # but a real marker outside the fence still is (lets a doc teach the convention safely)
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "doc.md"), "w") as fh:
            fh.write("<!-- DEPENDS_ON: real/outside.md -->\n```\n<!-- DEPENDS_ON: example/inside.md -->\n```\n")
        paths = {p for _, _, _, p in scan(d)}
    chk("9 fenced marker skipped, live marker kept",
        "real/outside.md" in paths and "example/inside.md" not in paths)

    # case 10 baseline round-trip: a 🔴 finding serializes and re-parses to the same key
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "src.md"), "w") as fh:
            fh.write("<!-- DEPENDS_ON: missing_dir/gone.md -->\n")
        red = [b for b in scan(d) if b[2] == "🔴"]
        bl_path = os.path.join(d, ".defines.baseline")
        with open(bl_path, "w") as fh:
            fh.write(_BASELINE_HEADER + "\n")
            for srcrel, typ, sev, path in red:
                fh.write(f"{srcrel}\t{typ}\t{path}\n")
        loaded = load_baseline(bl_path)
    chk("10 baseline round-trip key stable",
        len(red) == 1 and _key(red[0]) in loaded and len(loaded) == 1)

    # case 11 --check --baseline grandfathers a pre-existing 🔴, still flags a NEW one
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "old.md"), "w") as fh:
            fh.write("<!-- DEPENDS_ON: gone_old/x.md -->\n")
        baseline = {_key(b) for b in scan(d) if b[2] == "🔴"}      # snapshot the pre-existing 🔴
        with open(os.path.join(d, "new.md"), "w") as fh:           # introduce a NEW broken ref
            fh.write("<!-- DEPENDS_ON: gone_new/y.md -->\n")
        red_after = [b for b in scan(d) if b[2] == "🔴"]
        new_red = [b for b in red_after if _key(b) not in baseline]
    chk("11a baseline grandfathers the pre-existing 🔴", len(baseline) == 1)
    chk("11b new 🔴 not in baseline is still flagged",
        len(new_red) == 1 and "gone_new/y.md" in {b[3] for b in new_red})

    # case 12 dot-dir descent (0.2.1): a marker inside a hidden dir (.claude/…) IS scanned.
    # glob('**/*.md') skipped dot-dirs, silently missing markers exactly where agent rules live.
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, ".claude", "rules"))
        with open(os.path.join(d, ".claude", "rules", "x.md"), "w") as fh:
            fh.write("<!-- DEPENDS_ON: missing_dir/ghost.md -->\n# x\n")
        paths = {p for _, _, _, p in scan(d)}
    chk("12 dot-dir marker IS scanned (.claude descent)", "missing_dir/ghost.md" in paths)

    # case 13 find_dependents reverse lookup (0.2.2): every file whose DEPENDS_ON textually points at
    # a source — srcdir-rel ∪ root-rel normpath match, dot-dir descent, NON-dependents excluded. auth.md
    # is deliberately NOT created (the match is textual/existence-independent — works mid-rename).
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "rules"))
        os.makedirs(os.path.join(d, ".claude", "rules"))
        for rel in ("rules/login.md", "rules/session.md"):
            with open(os.path.join(d, rel), "w") as fh:
                fh.write("<!-- DEPENDS_ON: rules/auth.md -->\n# x\n")
        with open(os.path.join(d, ".claude", "rules", "x.md"), "w") as fh:
            fh.write("<!-- DEPENDS_ON: rules/auth.md -->\n# x\n")   # dot-dir dependent (must be found)
        with open(os.path.join(d, "other.md"), "w") as fh:
            fh.write("<!-- DEPENDS_ON: base.md -->\n# x\n")          # non-dependent (must be excluded)
        deps = find_dependents("rules/auth.md", root=d)             # root=d → scope to fixture, not global ROOT
    chk("13 find_dependents textual reverse match (incl dot-dir, excl non-dependent)",
        deps == sorted([".claude/rules/x.md", "rules/login.md", "rules/session.md"]))

    # ── concept-scoped DEPENDS_ON (0.3.0) ────────────────────────────────────────────────────
    # case 14 grammar parse: scope only when the tail is a bare slug (P1/P2/P3)
    chk("14a parse 'a#x' -> (a, x)", parse_depends_value("a#x") == ("a", "x"))
    chk("14b parse 'a' -> (a, None)", parse_depends_value("a") == ("a", None))
    chk("14c parse 'notes#1.md' -> (notes#1.md, None) [tail not a slug]",
        parse_depends_value("notes#1.md") == ("notes#1.md", None))

    # case 15 --concept filter: unscoped ∪ scoped-X ∪ fail-safe(invalid scope); EXCLUDES scoped-Y.
    # F1 include unscoped+scoped-X · F2 exclude scoped-Y · F3 no-concept=all · FS1 fail-safe · F4 both-edges
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "src.md"), "w") as fh:
            fh.write("<!-- DEFINES: alpha, beta -->\n# src\n")
        for rel, body in (
            ("dep_alpha.md",    "<!-- DEPENDS_ON: src.md#alpha -->\n"),
            ("dep_beta.md",     "<!-- DEPENDS_ON: src.md#beta -->\n"),
            ("dep_unscoped.md", "<!-- DEPENDS_ON: src.md -->\n"),
            ("dep_typo.md",     "<!-- DEPENDS_ON: src.md#gamma -->\n"),          # gamma ∉ DEFINES -> fail-safe
            ("dep_both.md",     "<!-- DEPENDS_ON: src.md#alpha -->\n<!-- DEPENDS_ON: src.md -->\n"),
        ):
            with open(os.path.join(d, rel), "w") as fh:
                fh.write(body)
        only_alpha = find_dependents("src.md", concept="alpha", root=d)
        only_beta = find_dependents("src.md", concept="beta", root=d)
        all_deps = find_dependents("src.md", concept=None, root=d)
    chk("15a --concept alpha: unscoped+scoped-alpha+fail-safe+both, EXCLUDES scoped-beta",
        only_alpha == sorted(["dep_alpha.md", "dep_unscoped.md", "dep_typo.md", "dep_both.md"]))
    chk("15b --concept beta EXCLUDES dep_alpha but keeps dep_both (it also has an unscoped edge)",
        "dep_alpha.md" not in only_beta and "dep_both.md" in only_beta)
    chk("15c no --concept returns ALL dependents (back-compat)",
        all_deps == sorted(["dep_alpha.md", "dep_beta.md", "dep_unscoped.md", "dep_typo.md", "dep_both.md"]))

    # case 16 concept-scope advisory: 🟡 on a #concept the target does NOT DEFINE; silent on a valid one;
    # NON-BLOCKING (scan surfaces 🟡 but no 🔴, so --check stays exit 0).
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "target.md"), "w") as fh:
            fh.write("<!-- DEFINES: realconcept -->\n# t\n")
        with open(os.path.join(d, "dep.md"), "w") as fh:
            fh.write("<!-- DEPENDS_ON: target.md#typoconcept -->\n# d\n")
        a_ok = validate_concept_scope("target.md#realconcept", d, d)
        a_bad = validate_concept_scope("target.md#typoconcept", d, d)
        findings = scan(d)
    chk("16a valid scope -> None (silent)", a_ok is None)
    chk("16b invalid scope -> 🟡 advisory", a_bad is not None and a_bad[0] == "🟡")
    chk("16c scan surfaces the 🟡 and NO 🔴 (non-blocking)",
        any(sev == "🟡" and "typoconcept" in p for _, _, sev, p in findings)
        and not any(sev == "🔴" for _, _, sev, p in findings))

    # case 17 DEFINES union across MULTIPLE header lines (S8): a target may split concepts over lines.
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "t.md"), "w") as fh:
            fh.write("<!-- DEFINES: one -->\n<!-- DEFINES: two -->\n# t\n")
        slugs = _read_defines_set(os.path.join(d, "t.md"), {})
        second_line_valid = validate_concept_scope("t.md#two", d, d)
    chk("17 DEFINES union across lines (#two on the 2nd DEFINES line is valid)",
        slugs == {"one", "two"} and second_line_valid is None)

    # case 18 DEFINES_EXEMPT is a PATH prefix, not a string prefix (N1): `examples` must not exempt `examples_extra`.
    chk("18a exempt a path under the prefix dir", is_exempt("examples/x.md", "rules/g.md", "", prefixes=("examples",)))
    chk("18b a sibling dir sharing the string is NOT exempt",
        not is_exempt("examples_extra/x.md", "rules/g.md", "", prefixes=("examples",)))

    # case 19 ReDoS guard (security hardening): CONTIG_TOK is O(n²) on a long no-extension value, so
    # extract_candidates bounds the scan to value[:512]. Teeth = a 50k-char no-ext value must finish
    # well under 1s (un-guarded ≈ 6s; guarded < 1ms) AND yield no candidates. Generous threshold so
    # the timing assertion does not flake under CI load.
    import time as _time
    _t0 = _time.perf_counter()
    _redos = extract_candidates("a" * 50000)
    _dt = _time.perf_counter() - _t0
    chk("19 long no-ext value is ReDoS-guarded (<1s, no candidates)", _dt < 1.0 and _redos == [])

    print(f"\n{'✅ self-test PASS' if not fails else '❌ FAIL: ' + ', '.join(fails)}")
    return 0 if not fails else 1


def main():
    args = sys.argv[1:]
    mode = args[0] if args else "--report"
    if mode == "--version":
        print(f"defines_provenance {__version__}")
        return
    if mode == "--self-test":
        sys.exit(self_test())
    if mode == "--baseline":
        sys.exit(write_baseline())
    if mode == "--dependents":
        source = args[1] if len(args) > 1 else None
        if not source or source.startswith("-"):
            print("error: --dependents requires a source path (e.g. --dependents rules/auth.md  | "
                  " --dependents rules/auth.md --concept session-rules)", file=sys.stderr)
            sys.exit(2)
        concept = None
        if "--concept" in args:
            i = args.index("--concept")
            concept = args[i + 1] if i + 1 < len(args) else None
            if not concept:
                print("error: --concept requires a concept slug "
                      "(e.g. --dependents rules/auth.md --concept session-rules)", file=sys.stderr)
                sys.exit(2)
        if concept is not None:
            # filtered fast-path: dependents relevant to ONE concept (scoped-to-it ∪ unscoped ∪ fail-safe)
            deps = find_dependents(source, concept=concept)
            print(f"# {len(deps)} file(s) DEPENDS_ON {source} relevant to #{concept} "
                  f"(scoped-to-it + unscoped + unrecognized-scope):")
            for d in deps:
                print(d)
            sys.exit(0)
        # unfiltered: flat when nothing is scoped (identical to pre-0.3.0), grouped once scoping is in play
        unscoped, groups = dependents_by_concept(source)
        total = len(unscoped) + sum(len(v) for v in groups.values())
        print(f"# {total} file(s) DEPENDS_ON {source}:")
        if not groups:
            for d in unscoped:
                print(d)
        else:
            if unscoped:
                print("── unscoped · always re-check ──")
                for d in unscoped:
                    print(d)
            for concept_key, files in groups.items():
                print(f"── concept: {concept_key} ──")
                for d in files:
                    print(d)
        sys.exit(0)
    broken = scan()
    red = [b for b in broken if b[2] == "🔴"]
    yellow = [b for b in broken if b[2] == "🟡"]
    if mode == "--check":
        baseline = set()
        if "--baseline" in args:
            i = args.index("--baseline")
            bpath = args[i + 1] if i + 1 < len(args) else None
            if not bpath:
                print("error: --baseline requires a file path "
                      "(e.g. --check --baseline .defines.baseline)", file=sys.stderr)
                sys.exit(2)
            baseline = load_baseline(bpath)
        new_red = [b for b in red if _key(b) not in baseline]
        if baseline:
            # stale-baseline note (eslint --prune-suppressions analog): entries no longer broken
            stale = baseline - {_key(b) for b in red}
            if stale:
                print(f"ℹ️  {len(stale)} baseline entry(ies) now resolved — "
                      f"regenerate with --baseline to burn down.", file=sys.stderr)
        if new_red:
            label = "new " if baseline else ""
            print(f"🔴 {len(new_red)} {label}broken DEFINES/DEPENDS target(s) (path contains a directory)")
            for s, t, sev, p in new_red:
                print(f"  {s} [{t}] {p}")
        sys.exit(1 if new_red else 0)
    # --report
    print(f"DEFINES/DEPENDS target scan: 🔴 {len(red)} (confident broken) | 🟡 {len(yellow)} (bare-name, verify)\n")
    for s, t, sev, p in broken:
        print(f"{sev} {s}  [{t}] {p}")


if __name__ == "__main__":
    main()
