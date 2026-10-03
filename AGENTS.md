# droid-review-skill

Skills in `skills/` (what users install), maintainer tooling in
`.claude/skills/maintain-droid-review-skill/`.

## Checks

```bash
.claude/skills/maintain-droid-review-skill/regress.sh             # every script path against a stub droid; no model cost, ~1 min
python3 .claude/skills/maintain-droid-review-skill/statusline_test.py
python3 .claude/skills/maintain-droid-review-skill/reviews_test.py
bash -n skills/*/*.sh && shellcheck skills/*/*.sh                  # report only new warnings
```

`regress.sh` runs both unit suites too. Changes to model shortcuts or droid's
catalog: see the maintain skill's SKILL.md.

## .droid-reviews/

Reviews, logs and run metadata accumulate there and are never pruned. The
folder ignores itself in git; deleting old files is safe.
