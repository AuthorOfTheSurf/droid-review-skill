# droid-review-skill

Skills in `skills/` (what users install), maintainer tooling in
`.claude/skills/maintain-droid-review-skill/`.

## Verification Suite

```bash

# Regression Suite: every script path vs. Stub `droid`
# no model cost, ~1 min (Requires `droid` installed)
.claude/skills/maintain-droid-review-skill/regress.sh

# Tests
python3 .claude/skills/maintain-droid-review-skill/reviews_test.py
claude plugin validate skills/droid-reviews && claude plugin test skills/droid-reviews   # the band (a Claude Code mod): its rows

# Lint
bash -n skills/*/*.sh && shellcheck skills/*/*.sh                  # report only new warnings
```

`regress.sh` runs the unit suite and the band's tests too (the band's only where the
installed `claude` has `plugin test`). When a run counts as stopped (its process gone, or
its log silent for `STALE_S`) is decided twice, in `skills/droid-review/runs.py` for the
history and in `skills/droid-reviews/hooks/rows.ts` and `register.tsx` for the band: a change
goes in both. Changes to model shortcuts or droid's catalog: see the maintain skill's SKILL.md.

## .droid-reviews/

Reviews, logs and run metadata accumulate there and are never pruned. The
folder ignores itself in git; deleting old files is safe.
