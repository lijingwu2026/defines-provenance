<!-- DEFINES: defines-depends-convention -->

# The DEFINES / DEPENDS_ON convention

A two-line, hand-written convention for declaring **structural provenance** in a library of
markdown rules, specs, or docs — so you (and your agent) can answer *"which file is the SOURCE
of this concept, and which files DEPEND on it?"* deterministically, instead of guessing from
semantic similarity.

It is just two HTML comments. No plugin, no build step, no database. The companion
`defines_provenance.py` checks the convention (it never writes your files); a small new-file hook
nudges you to tag files as you create them. Tooling assists — the structure stays declared by you.

---

## The two markers

Put them in the **header** of a file — after frontmatter (if any), before the first heading:

```markdown
---
title: Auth policy
---
<!-- DEFINES: auth-policy, session-rules -->
<!-- DEPENDS_ON: rules/base-policy.md -->

# Auth policy
...
```

- **`<!-- DEFINES: X, Y -->`** — *this file is the SOURCE of truth for concept `X` (and `Y`).*
  If two files disagree about `X`, the one that DEFINES it wins. Comma / `，` / `、` separated.
- **`<!-- DEPENDS_ON: <path> -->`** — *this file DERIVES from / references that SOURCE.*
  If the SOURCE changes, this file may need to be updated. The value is a path (or several), e.g.
  `rules/base-policy.md` as in the example above. A path **may** optionally suffix `#concept` — a slug
  the target's `DEFINES` declares — to scope the dependency to just that one concept
  (`rules/base-policy.md#session-rules`); a bare path means whole-file, the always-relevant default.

That is the whole vocabulary — two markers; the optional `#concept` scope is the one refinement.

### Which marker does the work — and when to add each

The two markers are **not symmetric**:

- **`DEPENDS_ON` is the dependency edge** — the load-bearing layer. The reverse lookup
  (`--dependents`) and the propagate loop run *entirely* on these; this is the relationship the tool
  actually mechanizes. An optional `#concept` scope narrows it: `--dependents <src> --concept X` lists
  only the dependents pinned to `X` (plus the always-relevant unscoped ones), and a `#concept` the
  target does **not** DEFINE fails safe — treated as unscoped, never silently dropped.
- **`DEFINES` is an authority label** — it answers only *"who wins if two files disagree about `X`?"*
  — powering the human SOURCE-overrides-DERIVED tie-break, not the dependency graph. `--check` resolves
  the *paths* in either marker; a bare `DEFINES` concept name (no `/`, no extension) is free text that
  no check constrains.

So tag a file only when it passes a one-line test:

- **`DEFINES: X`** — *is this the final say on `X`? does it win if another file disagrees?*
- **`DEPENDS_ON: <src>`** — *if `<src>` changes, might this file go stale?*

A **mention is not a dependency.** Prose that refers to "auth" does not `DEPENDS_ON` the auth policy —
it depends only if changing the policy would oblige you to change this file. Tag the load-bearing
links; leave the rest untagged.

---

## The one rule that makes it worth doing

> **SOURCE overrides DERIVED.** A concept has exactly one home (the file that `DEFINES` it).
> Every other mention is `DERIVED` and must stay in sync with the home — never the other way around.

This is the thing semantic search cannot give you. Two files can be semantically near-identical and
yet independent; two files can read as totally unrelated and yet one hard-depends on the other.
**Dependency is a human-declared structure, not a textual statistic** — so it has to be *written down*.
Once it is written down, a 200-line script can mechanically guarantee that every declared link still
points at something real.

---

## What the checker enforces (and what it deliberately does not)

`defines_provenance.py` verifies one narrow, fully-deterministic property:

> Every path referenced by a `DEFINES` / `DEPENDS_ON` marker **resolves to a file that exists.**

Severity:

| Result | Meaning |
|---|---|
| 🔴 **confident broken** | the value contains a directory (`rules/ghost.md`) and resolves nowhere → almost certainly a stale/typo'd path |
| 🟡 **bare-name, verify** | a name with no `/` (`ghost.md`) that resolves nowhere → ambiguous: could be a concept name, not a path |
| 🟡 **concept not found** | a `DEPENDS_ON … #concept` whose path resolves but whose `#concept` is **not** among the target's `DEFINES` → likely a typo; the scope is treated as unscoped (fail-safe) |
| (silent OK) | any candidate path resolves (and any `#concept` is one the target DEFINES), OR the value is a prose concept name with no file extension |

**Only 🔴 blocks** — `--check` exits 1 on a 🔴 and 0 otherwise; both 🟡 rows are advisory (surfaced by
`--report`, never a merge-blocker).

It does **not** check semantics, ownership conflicts, or whether your SOURCE/DERIVED labelling is
*correct* — only that the links are not dangling. In particular a `#concept` that names a *valid but
wrong* concept (one the target really DEFINES, just not the one this file derives from) passes silently —
no deterministic check can catch a wrong-but-valid scope; that stays your judgement (the propagation
content-grep below is the mitigation). It is a backstop for human forgetfulness (moved a file, fixed a
typo, renamed a dir), not a linter for your ideas.

### Escapes (for the inevitable edge cases)

- Per-line: add `<!-- DEFINES-EXEMPT: reason -->` on the same line to skip that marker.
- Per-tree: set `DEFINES_EXEMPT=changelog/,history/` to ignore broken targets under those prefixes
  (history/changelog files legitimately reference files that have since moved).

---

## Why "header only"?

The checker scans only the first ~60 lines of each file, because the convention is a *header*
convention. A `DEFINES:` appearing mid-file is almost always a changelog quote or an inline example
whose path is relative to some *other* file — scanning header-only removes that whole class of false
positives. If you want a marker checked, put it in the header.

---

## Keeping in sync — the completion cycle

The convention has **two upkeep moments**, both required: (1) **create-moment** — when you add a
new file, tag it before you forget (a new-file hook can nudge you); (2) **change-moment** — when
you change a SOURCE, find its dependents and re-sync them. The rules below cover the change-moment.

The markers earn their keep a second way: they close a **completion cycle** — *change a SOURCE → find
what now depends on it → complete the sync → verify the links* — so a change never silently leaves its
derived files behind. You answer *"if I change this SOURCE, what DERIVES from it and might now be
stale?"* **before** you forget, with a read-only reverse lookup for the *find* step:

```bash
python3 defines_provenance.py --dependents rules/auth.md
```

prints every file whose `DEPENDS_ON` points at `rules/auth.md`. It's a *textual* match (it works even
mid-rename, before the new path exists), and it does **not** require the target to exist.

The discipline is two rules:

- **Changed a SOURCE?** run `--dependents <that source>`, then re-check each file it lists and update the
  ones that drifted. **Changed only one concept?** `--dependents <src> --concept X` narrows the list to the
  dependents scoped to `X` (plus the always-relevant unscoped ones), and a quick content-grep of that
  concept's keywords catches any dependent that *should* have been scoped to `X` but was mis- or
  under-tagged. The checker proves the *link* still resolves; it cannot prove the *content* stayed in sync
  — that judgement is yours. (Which is exactly why this is a discipline, not an automated check.)
- **Changed a DERIVED file?** look at the SOURCE it `DEPENDS_ON` first — the home wins; don't fork the concept.

This is propagation by *convention + a reverse lookup*, **not** automatic content-drift detection. There is
no deterministic way to know a dependent's *meaning* went stale (that's the whole thesis — dependency isn't
in the text). `--dependents` makes the *who-to-check* list free; you still do the checking.

---

## Honest scope

This convention was evolved by one person, for one corpus, over about six weeks (see `README.md` for
the story). It demonstrably keeps annotation **coverage** high and catches **dangling paths**. It has
**not** been measured for catch-rate against real contradictions, or for false-positive rate, at scale
or across other people's corpora. It is a small sharp tool that earns its keep; it is not a proven
methodology. Adopt the *idea* (declare provenance, check it mechanically); measure it on your own data.

The **concept-scope** refinement (`#concept`) is **opt-in**: declare a single-slug concept the SOURCE's
`DEFINES` carries, and an edge can depend on just that concept (whole-file `DEPENDS_ON` stays the always-safe
default). It needs a **single-slug** concept name as a precondition — a SOURCE that names concepts in prose
gives them a slug first (the description can ride along in a trailing `(…)`), and an edge that carries its own
trailing prose annotation must put the `#concept` last or stay whole-file. It is mechanism-tested **and
dogfooded on the author's own multi-concept sources** (`vault-iterate`, `plan-gates`): focused dependents —
e.g. ADR/decision docs where one doc tracks one concept — scope cleanly, while broad consumers that depend on
many concepts stay whole-file through the fail-safe (the correct outcome, not a miss). Its mis-attribution
miss-rate is still unmeasured and the fail-safe is conservative by design — reach for scoping on genuinely
multi-concept SOURCEs; whole-file `DEPENDS_ON` remains the always-safe default.
