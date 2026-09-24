---
name: update-model-shortcuts
description: Maintainer pass over the model shortcut table in skills/droid-review/droid-review.sh — compare it with the models the installed droid CLI offers, present what changed, and apply only the shortcuts the user picks. Run only when the user asks to update, refresh, or check the droid model shortcuts.
---

# Update the model shortcuts

The shortcut table is the one part of this repo that goes stale on its own:
droid ships a model and `opus` keeps pointing at the old one, with no error,
because the old id still validates. This pass finds that drift. **Which models
earn a shortcut is the user's judgment, not yours** — gather the evidence,
recommend, and change only what they pick.

## 1. Get current

```bash
git pull
droid --version
droid exec --help
droid exec -m x --list-tools   # "Invalid model", then every id droid accepts
skills/droid-review/droid-review.sh --models
```

If droid itself is behind, the list is too; say so, and let the user decide
whether to update droid first.

## 2. Compare

The ids come from the `--list-tools` error, not the help: `droid exec --help`
lags behind it, missing new models (Opus 5.5 and the GPT-6 family went a
release or more without appearing) and still listing retired ones. The help's
`Model details` is still the only place efforts are given; for a model it does
not list, ask the user to read the levels from `/model` in interactive droid.
Do not probe with a real run: droid runs an unsupported effort without
complaint, so a reply proves nothing.

Read those ids against `shortcut()` in the script. Report, in one table
(shortcut → current → candidate → why):

- **A newer model in a shortcut's family.** Do not assume the listing order is
  newest first: it is not (`gemini-3.1-pro-preview` sits above
  `gemini-3.8-flash`). Compare version numbers, and name what kind of change it
  is — a version bump, a different tier (pro vs. flash), a `-fast` variant, a
  preview. Only a plain version bump is a like-for-like move; the rest are
  choices.
- **A shortcut's model marked `[Deprecated]` or gone.** These break for users
  once droid drops the id, so lead with them.
- **A pinned effort the model no longer supports**, or a newer model whose
  supported levels differ from the pin (a pin of `max` cannot carry over to a
  model that tops out at `high`).
- **Families with no shortcut yet** (kimi, deepseek, …), listed briefly. Do not
  propose adding them unless the user asks; a short table is the point.

If nothing drifted, say that in one line and stop.

## 3. Apply what the user picks

Edit `shortcut()`, the droid version in the comment above it, and the shortcut
table and version note in README.md — the three must agree. Update the
`argument-hint` line in both `skills/*/SKILL.md` only if a shortcut name was
added or removed. Then verify every shortcut against the real catalog without
running a review:

```bash
ids="$(droid exec -m x --list-tools 2>&1 >/dev/null | tr ',' '\n' | awk '{print $1}')"
skills/droid-review/droid-review.sh --models | while read -r s id effort; do
  grep -qxF "$id" <<<"$ids" && echo "$s $id ok" || echo "$s $id MISSING"
done
```

Check each pinned effort against that model's `supported:` list by eye, or
against what the user read from `/model` when the help does not list it; the
script enforces it at run time only for models the help details, so a bad pin
should not reach a user first.

## 4. Commit

One commit, title only, naming the moves (e.g. `Shortcuts: opus → claude-opus-5-1,
drop deprecated minimax`). Push when the user agrees. Users who installed by
symlink pick it up on their next `git pull`; there is nothing to restart.
