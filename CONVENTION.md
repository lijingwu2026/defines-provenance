<!-- DEFINES: defines-depends-convention -->

# The DEFINES / DEPENDS_ON convention

A two-line, hand-written convention for declaring **structural provenance** in a library of
markdown rules, specs, or docs — so you (and your agent) can answer *"which file is the SOURCE
of this concept, and which files DEPEND on it?"* deterministically — instead of inferring it from
similarity, or hand-wiring it as an undirected backlink web.

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
  `rules/base-policy.md` as in the example above. A path may suffix `#concept` — a slug the target's
  `DEFINES` declares — to scope the dependency to one concept (`rules/base-policy.md#session-rules`).
  **Scope a focused dependent at creation** (one that derives from just one of the SOURCE's concepts); a
  **broad consumer** stays a bare path — whole-file, the always-safe default.

That is the whole vocabulary — two markers; the optional `#concept` scope is the one refinement.

**Think of it as a dictionary.** `DEFINES: X` is the **dictionary entry** — this file owns concept `X`;
every other mention defers to it. `DEPENDS_ON` is a **citation** of an entry, in three forms: the **whole
file** (`B`), a **single concept** (`B#X`), or **several** (multiple `DEPENDS_ON` lines — `B#X` + `C#Y`,
or `B#X` + `B#Y` to track two of B's concepts but not the rest). The checker just verifies each citation
points at something real — the path resolves, and a `#X` is one the entry actually `DEFINES`.

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

Four parties each declare one thing — which is why nothing here is redundant:

| who | declares | what it buys |
|---|---|---|
| **`DEFINES: X`** (in the SOURCE) | the SOURCE owns concept `X` — its one home | provenance (the authoritative home) + a legal dictionary of concept names |
| **`#X`** on a `DEPENDS_ON` edge | which of the SOURCE's concepts this dependent tracks | triage precision — *who* gets pulled in to re-check when `X` changes |
| **you**, editing the SOURCE | which concept *this* edit changed | the one bit only a human knows |
| **the checker** | each `#X` is a real entry in the target's `DEFINES`; joins "you changed `X`" × every edge's `#X` | verification + filtering |

`DEFINES` is never there to *detect which concept changed* — that's the `declare, don't infer` line the tool won't cross. It (1) declares `X`'s authoritative home (provenance) and (2) gives `#X` a real dictionary to check against. Precision lives on the dependent's side, ownership on the SOURCE's, change-detection in your head.

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

This is the thing **no similarity graph — and no backlink web — gives you.** Two files can be semantically
near-identical yet independent; two can read as unrelated yet one hard-depends on the other; and a backlink
that says they *relate* never says **which is the SOURCE and which must track it.**
**Dependency is a human-declared, directional structure — not a textual statistic, not an undirected web** — so it has to be *written down*.
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
*correct* — only that the links are not dangling. *(One miss it can't catch: a `#concept` naming a
valid-but-wrong concept passes silently — the propagation content-grep is the mitigation.)* It is a
backstop for human forgetfulness (moved a file, fixed a typo, renamed a dir), not a linter for your ideas.

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

The **concept-scope** refinement (`#concept`) is **scoped at creation, by default** for focused dependents —
not an opt-in afterthought: when a doc derives from just one concept the SOURCE's `DEFINES` carries, scope
its edge to that concept then; whole-file `DEPENDS_ON` stays the always-safe default for broad consumers,
with no re-tag burden later. It needs a **single-slug** concept name as a precondition: a SOURCE that names its concepts in prose gives
them a slug first (the description can ride in a trailing `(…)`). And keep `#concept` as the edge's **last**
token — an edge with its own trailing prose annotation must put `#concept` last, or else stay whole-file. It is mechanism-tested **and
dogfooded on the author's own multi-concept sources** (`vault-iterate`, `plan-gates`): focused dependents —
e.g. ADR/decision docs where one doc tracks one concept — scope cleanly, while broad consumers that depend on
many concepts stay whole-file through the fail-safe (the correct outcome, not a miss). Its mis-attribution
miss-rate is still unmeasured and the fail-safe is conservative by design — reach for scoping on genuinely
multi-concept SOURCEs; whole-file `DEPENDS_ON` remains the always-safe default.
