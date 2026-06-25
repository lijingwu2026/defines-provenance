<!-- DEPENDS_ON: CONVENTION.md, ONBOARDING.md -->

# Reference hooks for defines-provenance

Two small reference hooks — one per upkeep moment (both moments matter; adapt them to your runtime):

- **`defines_trigger_hook.py`** — the **TRIGGER** (primary). When you *change* a SOURCE, it
  auto-runs `--dependents` and hands you the DERIVED files to re-check. The sections below are about it.
- **`defines_tag_nudge_hook.py`** — the **companion** that nudges you to tag a *new* file that
  lands in an area you've already been tagging (last section: [§Companion hook](#companion-hook--keep-new-files-tagged)).

Both are **references**, not turnkey files; both fail-open (never block an edit); neither auto-edits — they only remind.

## The trigger hook — what it does

`defines_trigger_hook.py` is the **TRIGGER** stage of the lifecycle: it makes the
`change a SOURCE → find what depends on it → re-check` loop fire **automatically**,
instead of you remembering to run `--dependents` by hand.

The trigger is the one piece you wire into *your* runtime. This folder ships the Claude Code shape; the
other runtimes are one-for-one variants (see [`../../ONBOARDING.md`](../../ONBOARDING.md) §Wire the trigger).

On every `Edit`/`Write` of a `.md` file that contains a `<!-- DEFINES: … -->` marker
(i.e. a SOURCE), it runs `defines_provenance.py --dependents <file>` and prints the
DERIVED files your agent should re-read. It **fail-opens** on any error and only writes
to stderr — it never blocks an edit.

```
[defines-trigger] You changed SOURCE rules/commit.md. Re-check its DERIVED files:
  ── unscoped · always re-check ──
    - CLAUDE.md
  ── concept: branch-policy ──
    - agents/reviewer.md
  ── concept: commit-format ──
    - skills/ship.md
  (changed one concept? add `--concept <name>` to narrow; then `defines_provenance.py --check` before commit to prove no link dangles)
```

When the SOURCE declares more than one concept, the list is **grouped** — an `unscoped · always re-check`
block (edges that point at the whole file) followed by one block per concept — so if you only touched one
concept you can re-check just that block (and `--concept <name>` narrows the command itself). A
single-concept SOURCE prints the same flat list as before; grouping only appears once a scoped edge exists.

## Wire it into Claude Code (drop-in, 3 steps)

1. Copy `defines_trigger_hook.py` into your repo (e.g. `.claude/hooks/`).
2. Register it as a `PostToolUse` hook in `.claude/settings.json`:

   ```json
   {
     "hooks": {
       "PostToolUse": [
         { "matcher": "Edit|Write",
           "hooks": [ { "type": "command",
                        "command": "python3 .claude/hooks/defines_trigger_hook.py" } ] }
       ]
     }
   }
   ```
3. If `defines_provenance.py` isn't at your repo root, point the hook at it:
   `export DEFINES_CHECKER=/path/to/defines_provenance.py`.

That's it — this is the *same* PostToolUse mechanism Claude Code injects for any
project, so for a Claude Code adopter it is a literal drop-in (no adaptation).

## Configuration

| env | default | purpose |
|---|---|---|
| `CLAUDE_PROJECT_DIR` | cwd | repo root (Claude Code injects it automatically) |
| `DEFINES_CHECKER` | `<root>/defines_provenance.py` | where you vendored the checker |

## Variants

- **Richer Claude Code output:** instead of stderr you can emit
  `{"hookSpecificOutput": {"additionalContext": "…"}}` JSON so the derived list lands
  directly in the agent's context. The stderr form is kept minimal so the same body
  also works as a plain `pre-commit` script.
- **git / CI / Codex / Cursor:** same pattern (file-change → `--dependents` → re-read),
  different surface — recipes in [`../../ONBOARDING.md`](../../ONBOARDING.md) §Wire the trigger.

## Companion hook — keep new files tagged

`defines_tag_nudge_hook.py` covers the *other* upkeep moment. The trigger hook fires when you **change**
a SOURCE; this one fires when you **create** a new `.md` and reminds you to declare its provenance — so a
new file doesn't silently escape the convention. It **never tags for you** (declare-don't-infer); it only
prints a one-line stderr reminder, and only inside an area you've already been tagging.

> This is the **Claude Code** (PostToolUse) path. The universal path for **any** runtime — and the way to
> make your agent declare new files *proactively* rather than after a nudge — is a one-line rule in your
> agent's root file; see [`../../ONBOARDING.md`](../../ONBOARDING.md#wire-the-trigger--close-the-loop-automatically) (the new-file case).

**What it does.** On `Edit`/`Write` of a new file (one git doesn't yet track) that has **no** marker, it
nudges you *if* the file is in scope:

```
[defines-tag] New file rules/new-rule.md sits in a provenance-tagged area but declares no
  <!-- DEFINES: --> / <!-- DEPENDS_ON: -->. If it owns a concept or derives from one,
  tag it (see CONVENTION.md). If it is neither, ignore this.
```

**Scope — zero-config (the false-positive control).** By default a file is "in scope" when its **own
directory already contains another `.md` that DEFINES a concept** — i.e. you've already established
provenance there. So it won't nag every new README or scratch note, only new files in dirs you're already
tagging.

> ⚠️ **Limit:** the auto-scope checks the file's *own directory* only. A new file in a **fresh
> subdirectory** of a tagged tree (or a top-level file when all your markers live deeper) gets **no**
> nudge. Set `DEFINES_SCOPE=rules/,specs/` (comma-separated path prefixes) to scope explicitly instead.

**Wire it (2 steps).** Keeping new files declared is necessary; this hook makes the reminder active (or
run a periodic `defines_provenance.py --report` as the no-agent alternative). It works independently of the propagate trigger:

1. Copy `defines_tag_nudge_hook.py` into your repo (e.g. `.claude/hooks/`).
2. Register it as a `PostToolUse` hook on the same `Edit|Write` matcher (alongside the trigger hook):

   ```json
   { "matcher": "Edit|Write",
     "hooks": [ { "type": "command",
                  "command": "python3 .claude/hooks/defines_tag_nudge_hook.py" } ] }
   ```

**Verify it in your env:** `python3 defines_tag_nudge_hook.py --self-test` — hermetic (builds a throwaway
git repo, checks the 6 scope cases: nudge in a tagged dir · silent in an untagged dir · silent if already
marked · silent if tracked · `DEFINES_SCOPE` match/no-match). Exit 0 = pass.

| env | default | purpose |
|---|---|---|
| `CLAUDE_PROJECT_DIR` | cwd | repo root (Claude Code injects it automatically) |
| `DEFINES_SCOPE` | _(auto: dirs that already have a `DEFINES` sibling)_ | comma-separated path prefixes to scope explicitly |
