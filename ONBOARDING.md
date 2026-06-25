<!-- DEFINES: onboarding-flow -->
<!-- DEPENDS_ON: CONVENTION.md -->

# Adopting it on a library you already have

The [README](README.md) has the 30-second version. This is the full walkthrough for retrofitting the
convention onto a mature, **already-untagged** library.

Onboarding is **LLM-assisted**: you hand the library to an AI agent, it *drafts* the provenance
markers, and you *confirm* them — staying at review scale, not data-entry scale (§2). It ends by wiring
the loop to fire on its own: **[§Wire the trigger](#wire-the-trigger--close-the-loop-automatically)**. It also covers the **create-moment** — tagging a new file as it lands — in the same section.

> **Before you start.** You need an AI coding agent (Claude Code / Codex / Cursor / …) and Python 3
> (standard library only — nothing to install). Budget ~30–60 min for a 50–200-file library — most of it
> is *you reviewing* the agent's draft, not tagging by hand.

## The mental model first

The checker only **checks** the links you declare — it **never writes your files, and never guesses
which files relate to which.** Dependency **can't be inferred**: a tool that scanned your library and
"figured out" the graph would just be handing you semantic *similarity* again — the exact thing that
does **not** answer "which file actually depends on this one." So the structure has to be **declared.**

LLM-assisted onboarding doesn't break that rule — it *splits* it. The agent **drafts** proposals (it
applies a written criterion to your files — the two tests below — not a filename guess); **you declare**
by reviewing and confirming each one. Your confirmation *is* the declaration: the LLM proposes, you own.
**You declare, the tool guards** — the agent just gets you to a reviewable draft faster than hand-scanning
a thousand files.

## 1 — Add the two markers

Put them in the header — after frontmatter, before the first heading (the checker only reads the first
~60 lines of a file):

```markdown
<!-- DEFINES: code-style -->     ← in the SOURCE file, e.g. .claude/rules/code-style.md
                                   the value is the CONCEPT this file owns (not a path)
# Code style
...

<!-- DEPENDS_ON: .claude/rules/code-style.md -->   ← in a file that derives from it, e.g.
                                                     .claude/rules/testing.md
                                                     the value is the SOURCE file's path
# Testing
Match the project's code style when writing tests ...
```

## 2 — Tag the library: the LLM-assisted flow

Don't hand-scan a thousand files — hand the library to an AI agent. It *drafts* the markers; you
review *proposals*, not raw files. Five steps (the agent does the heavy lifting; you decide):

| # | the agent does | you do |
|---|---|---|
| **0** prereq | vendor `defines_provenance.py` into your repo | — |
| **1** scan + classify | read the whole library; rank the likely SOURCEs (root instructions, domain rules, agent/skill defs, specs, registries are the usual suspects — a *prior*, not a verdict) | — |
| **2** propose SOURCEs | draft a `DEFINES` concept name + a reason for each top candidate | review the table |
| **3** propose DEPENDS_ON | draft the dependency edges via the two tests + a reason for each | review the table |
| **4** write | write the confirmed markers into the file headers | — |
| **5** close | baseline any pre-existing breakage (§3) + wire the trigger | confirm |

It proposes in **two tables** — every proposal surfaced, nothing written until you've seen it:

| SOURCE proposal | `DEFINES` name | why — *final say on X / the root* | confidence | action |
|---|---|---|---|---|
| `rules/code-style.md` | `code-style` | other rules defer to it on formatting | high | _(accept)_ |
| `notes/scratch.md` | `code-style`? | mentions style a lot, but defers to the rule | low | reject |

| DEPENDS_ON proposal | depends on | why — *source change → goes stale* | confidence | action |
|---|---|---|---|---|
| `rules/testing.md` | `rules/code-style.md` | "match the project's code style" — changes if it does | high | _(accept)_ |
| `faq.md` | `rules/code-style.md` | names it once in passing | low | reject |

A DEPENDS_ON edge may **optionally** scope to a single concept the source owns — `rules/code-style.md#code-style`
— when the file derives from just that one concept (a multi-concept source). It's opt-in; a bare path means
whole-file, the always-relevant default. (A `#concept` column is *not* needed — write the scope inline.) Keep
the `#concept` as the **last** token of the value — a trailing `(note)` *after* it is not parsed as a scope,
so either drop the note or leave the edge whole-file.

**Review the whole set — but you don't touch every row.** `action` defaults to **accept**: leave a row
to take it, edit only the ones you want to **rename** or **reject**. *Confidence* is a triage aid — it
tells you *where to look hardest* (low = the agent is unsure the test passes cleanly), it never lets a
row skip your eye. Confidence = **how cleanly a row passes the tests below**, not a filename match.

**Run every proposal through this checklist** — the agent drafts against it; you confirm against it:

1. **`DEFINES: X`** — *the final say on `X`: does it win if another file disagrees?* (not a file that merely *mentions* X)
2. **`DEPENDS_ON: <src>`** — *if `<src>` changes, might this file go stale?* (a **mention is not a dependency**) — optionally scope it `<src>#concept` when you derive from just one concept the source owns.
3. **One home per concept** — no two files `DEFINES` the same `X`.
4. **The concept name is the concept the file *owns*** — never invented, never a file path.
5. **SOURCE overrides DERIVED** holds — the `DEFINES` file is the one that wins a disagreement.

### Setup prompt

Paste this at your library root, into Claude Code / Codex / Cursor — it drives the whole flow above:

```text
Vendor defines_provenance.py (the single checker file from the defines-provenance bundle) into this
library. Read ALL my markdown files and PROPOSE, in TWO tables, which files are SOURCES (each owns a
concept nothing else may override) and which DEPEND ON them. Use two tests — DEFINES? = "is this file
the final say on X: does it win if another file disagrees?"; DEPENDS_ON? = "if the source changes, might
this file go stale?" (a mention is not a dependency). A DEPENDS_ON edge MAY optionally scope to ONE
concept the source DEFINES — write src#concept (e.g. rules/auth.md#session-rules) when the file derives
from just that one concept; otherwise leave it whole-file (the default). For each row give: the file,
the proposed concept name (or the source it depends on), a
one-line reason, and a confidence = how cleanly it passes the test (NOT a filename match). Run every
proposal through this checklist: (1) DEFINES = final say, not a mention; (2) DEPENDS_ON = real
dependency, not a mention; (3) exactly one home per concept; (4) concept name = the concept owned, never
a file path, never invented; (5) SOURCE overrides DERIVED. DRAFT only — never write a marker, invent a
name, or tag freely until I confirm. Surface ALL proposals so I review the whole set: I accept a row by
leaving it, and rename or reject the ones I change. After I confirm, write the markers, then wire the
trigger hook so edits re-check dependents automatically.
When you CREATE a new .md file, tag it: add <!-- DEFINES: X --> if it owns a concept or <!-- DEPENDS_ON: <src> --> if it derives from one, per CONVENTION.md.
```

> **Tip — a second pair of eyes (optional).** If your runtime supports it, after the draft, open a
> *fresh* context with a **different model** and have it audit the proposals against the same five
> checkpoints before you confirm — an independent read catches the over-confident calls a model is
> blind to in its own work. No second model? Walk the set against the checklist yourself.

You stay in the loop the whole way: the agent *drafts*, you *declare*; it never auto-tags.

## 3 — Already have broken links? Don't fix everything first

Snapshot the existing breakage and gate only *new* breakage — the ESLint-suppressions /
gitleaks-baseline pattern. Walked through:

```bash
# day 1 — you tag the library; 3 references are already stale (files since moved/renamed):
$ python3 defines_provenance.py --check
🔴 onboarding.md [DEPENDS_ON] rules/commit-convention.md
🔴 faq.md        [DEPENDS_ON] rules/old-auth.md
🔴 api-guide.md  [DEPENDS_ON] rules/v1-format.md
exit 1                    # CI would block you — but you can't fix all 3 right now

# snapshot them so CI is green TODAY (the 3 are grandfathered):
$ python3 defines_provenance.py --baseline > .defines.baseline    # commit this file
$ python3 defines_provenance.py --check --baseline .defines.baseline
exit 0

# a NEW broken link is still caught — that's the whole point:
$ python3 defines_provenance.py --check --baseline .defines.baseline
🔴 new-rule.md [DEPENDS_ON] rules/ghost.md
exit 1                    # only the new one; the 3 grandfathered stay silent

# pay it down over time — fix one, the tool tells you, then re-snapshot a smaller baseline:
$ python3 defines_provenance.py --check --baseline .defines.baseline
ℹ️ 1 baseline entry now resolved        # you repointed onboarding.md at the real file
$ python3 defines_provenance.py --baseline > .defines.baseline    # baseline now has 2 entries
# …repeat until empty → delete .defines.baseline → plain --check now guards everything.
```

## Keeping it in sync

Markers earn their keep a second way: before you change a SOURCE, ask *who derives from it?* The
checker has a read-only reverse lookup:

```bash
python3 defines_provenance.py --dependents .claude/rules/code-style.md
```

It lists every file whose `DEPENDS_ON` points at that source — a *textual* match that works even
mid-rename (the new path needn't exist yet). It tells you **who to re-check**; whether their content
actually drifted is a judgement only you can make. The checker proves the *link* resolves; it does not
claim to detect content drift (that would be inferring dependency again).

Changed only **one concept** of a multi-concept source? `--dependents <src> --concept X` narrows the list
to the dependents scoped to `X` plus the always-relevant unscoped ones — and a `#concept` the source does
not DEFINE fails safe (treated as unscoped, never dropped). Pair it with a quick content-grep of that
concept's keywords to catch any dependent that *should* have been scoped to `X` but was mis- or under-tagged.

The other upkeep moment is creation: when you add a new file, tag it before it escapes the convention — the next section wires that automatically.

## Wire the trigger — close the loop automatically

`--dependents` above is the *manual* version: it only fires when **you** remember to run it. The
**trigger** is the stage that fires it for you — on every edit of a SOURCE, your agent (or your CI) is
handed the DERIVED list automatically, so a change never silently leaves its dependents behind. This is
the one stage you wire into *your* runtime. The pattern is identical everywhere — *file changed →
`--dependents` → re-read* — only the surface differs.

**What it covers — and the new-file case.** The trigger only fires for a file that *already* declares a
concept (`<!-- DEFINES: -->`), so it automates one direction: *change an existing SOURCE → re-check its
DERIVED*. It never tags for you. So when you **create** a file:

- a new **SOURCE** — you add its `<!-- DEFINES: -->` tag (a declaration, never auto-inferred); once
  tagged, the trigger covers it from then on.
- a new **DERIVED** file — you add its `<!-- DEPENDS_ON: -->`; a dangling target is caught by **`--check`**
  (the pre-commit / CI gate), not the per-edit trigger.
- an **untagged** new file — declare it before it silently escapes the convention. Catch it **per your
  runtime**, the same way you wired the trigger:
    - **Any agent** (Claude Code / Codex / Cursor / …) — the surest path is one line in your agent's root
      file (`AGENTS.md` / `CLAUDE.md` / `.cursorrules`): *"when you create a new `.md`, add
      `<!-- DEFINES: X -->` if it owns a concept or `<!-- DEPENDS_ON: <src> -->` if it derives from one, per
      CONVENTION.md."* The agent then declares new files proactively — this is how the reference vault does
      it, and it works in **any** runtime.
    - **Claude Code** (PostToolUse) — instead of, or alongside, the instruction, drop in the companion
      **`defines_tag_nudge_hook.py`** so a new untagged `.md` in an already-tagged directory nudges
      automatically (auto-scoped; `DEFINES_SCOPE` widens it / covers fresh subdirs). If your runtime *also*
      exposes post-edit hooks (Codex `config.toml`, etc.), the same hook works — but **verify the hook key +
      stdin shape against your runtime** before relying on it (it fail-opens, so a mismatch just means no
      nudge). Recipe: [`examples/hooks/README.md`](examples/hooks/README.md#companion-hook--keep-new-files-tagged).
    - **No agent** (plain git / CI) — a periodic `--report` lists what's still untagged (the checker flags
      *dangling* links, not *missing* tags, so this is the catch-all).

  None of these auto-tag — you declare.

**Claude Code (literal drop-in).** Copy the reference hook and register it as a `PostToolUse` hook —
the same mechanism Claude Code already runs for every project, so there's nothing to adapt:

```bash
cp examples/hooks/defines_trigger_hook.py .claude/hooks/
```
```json
// .claude/settings.json
{ "hooks": { "PostToolUse": [
  { "matcher": "Edit|Write",
    "hooks": [ { "type": "command",
                 "command": "python3 .claude/hooks/defines_trigger_hook.py" } ] }
] } }
```
Full recipe + env vars (`DEFINES_CHECKER` if the checker isn't at repo root):
[`examples/hooks/README.md`](examples/hooks/README.md).

**git pre-commit (any runtime, no agent).** Block *new* dangling links and print the DERIVED files to
re-check — plain shell:

```sh
# .git/hooks/pre-commit   (chmod +x)
python3 defines_provenance.py --check || exit 1          # add --baseline .defines.baseline if you snapshotted (§3)
for f in $(git diff --cached --name-only --diff-filter=ACM | grep '\.md$'); do
  head -60 "$f" | grep -q '<!-- DEFINES:' || continue    # only SOURCEs
  echo "[defines] changed SOURCE $f — re-check its DERIVED:" >&2
  python3 defines_provenance.py --dependents "$f" >&2
done
```

**GitHub Actions (CI gate).** Fail any PR that introduces a dangling link:

```yaml
# .github/workflows/defines.yml
name: defines-provenance
on: pull_request
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 defines_provenance.py --check   # add --baseline .defines.baseline if you snapshotted
```

**Codex / Cursor / other agents.** The always-works path is one instruction in your agent's root file
(`AGENTS.md`, `.cursorrules`, …) — no runtime hook needed:

> When you edit a file containing `<!-- DEFINES: -->`, run
> `python3 defines_provenance.py --dependents <file>` and re-read every file it lists before you finish.

And: when you create a new `.md` file, add `<!-- DEFINES: X -->` if it owns a concept or `<!-- DEPENDS_ON: <src> -->` if it derives from one, per CONVENTION.md.

If your runtime *also* exposes programmatic post-edit hooks (Codex `config.toml`, etc.), wire the same
`defines_trigger_hook.py` as in Claude Code — but **verify the hook key + stdin shape against your
runtime's own version** before relying on it. The script fail-opens, so a shape mismatch degrades to
"no reminder," never a blocked edit.

---

Configuration is all optional, via environment: `DEFINES_ROOT`, `DEFINES_EXCLUDE`, `DEFINES_EXEMPT`.
Worked examples ship in [`examples/`](examples/); the convention itself is one screen —
**[CONVENTION.md](CONVENTION.md)**.
