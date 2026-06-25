# Examples

Two tiny fixtures that double as the first-run demo and as the regression anchor for upgrades.

> Run all commands below from the **repo root** (where `defines_provenance.py` lives), so the
> relative `DEFINES_ROOT=examples/...` resolves correctly.

## `clean/`

Every `DEFINES` / `DEPENDS_ON` marker resolves. The checker reports nothing and exits 0.

```bash
DEFINES_ROOT=examples/clean python3 defines_provenance.py --check    # exit 0
```

- `index.md` — DEFINES `project-conventions` (the SOURCE).
- `auth.md` — DEPENDS_ON `index.md` (resolves to a sibling).
- `sub/detail.md` — DEPENDS_ON `../auth.md` (resolves one directory up).

## `broken/`

One marker points at a file that does not exist. The checker flags **exactly** that one and exits 1.
`good.md` resolves and must **not** be flagged — that is the false-positive / false-negative guard:
the checker has to discriminate, not flag everything.

```bash
DEFINES_ROOT=examples/broken python3 defines_provenance.py --check   # exit 1
# 🔴 bad.md [DEPENDS_ON] rules/ghost.md
```

- `index.md` — DEFINES `example-broken-fixture` (the SOURCE).
- `good.md` — DEPENDS_ON `index.md` (resolves; must stay silent).
- `bad.md` — DEPENDS_ON `rules/ghost.md` (does not exist → 🔴).

### Baseline (grandfather the pre-existing 🔴, gate only new breakage)

The same `broken/` fixture shows the adoption workflow: snapshot the current 🔴, and a subsequent
`--check --baseline` passes — it would only fail if a *new* broken marker appeared.

```bash
DEFINES_ROOT=examples/broken python3 defines_provenance.py --baseline > /tmp/demo.baseline
DEFINES_ROOT=examples/broken python3 defines_provenance.py --check --baseline /tmp/demo.baseline  # exit 0
# the pre-existing rules/ghost.md is grandfathered; a NEW broken ref would still exit 1
```
