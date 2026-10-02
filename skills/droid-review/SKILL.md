---
name: droid-review
description: Second-opinion code review of the current branch from Factory's droid (GLM by default, any droid model), triaged against the code, fixed, and re-checked. Human-invoked, near merge — run only when the user asks for a droid review or to triage one, never on your own initiative. For a review that is not droid's structured code review, use droid-feedback instead.
argument-hint: "[glm|gemini|luna|auto|fable|opus|astra|sol|grok|qwen|kimi|deepseek|a,b,c] [effort] [focus]"
---

# droid review → triage → fix → re-check

The loop the user used to run by hand (droid tab → `/review` → paste into
Claude → "please triage this") is one command now. You run it end to end.

**Where the script is.** It sits next to this file — that is
`.claude/skills/droid-review/droid-review.sh` for a project install and
`~/.claude/skills/droid-review/droid-review.sh` for a global one. Use whichever
directory this SKILL.md was loaded from, and substitute it below.

**Which skill.** This one runs droid's own `/review`: a structured code review
that reports severity, file:line, and the scenario that breaks. When the user
wants something else — the copy, the API shape, "is this approach sane" — that
is the **droid-feedback** skill, which asks droid in plain words instead.

## 1. Get the review

```bash
.claude/skills/droid-review/droid-review.sh
.claude/skills/droid-review/droid-review.sh --uncommitted
.claude/skills/droid-review/droid-review.sh "$ARGUMENTS"
```

**Pass `$ARGUMENTS` through verbatim, as one argument — do not pick the model
yourself.** The script reads it: a first word that is exactly a shortcut
(`luna`, `gemini`, …) or a droid model id picks the model, a second word that
is exactly an effort level (`high`, `max`, …) overrides that model's level, and
the rest is optional emphasis on top of `/review`. So `/droid-review luna the
auth changes` is Luna at droid's default effort, weighted toward auth. No
shortcut pins an effort: a higher one is opt-in, only when the user names it. `--models`
prints the shortcuts, `--efforts [model]` every level a model
takes and its default, `--whats-new` what droid marks new, on sale or
deprecated; an effort the model does not support
fails before droid runs, so relay that message. Only when the user names a
model in prose the script cannot read ("use the Gemini one") translate it to
the shortcut or `--model`. The base branch is detected (origin/HEAD, else
main/master); `--base` overrides.

**No config file is needed.** droid loads AGENTS.md / CLAUDE.md by itself, and
the prompt tells it to read that for how the repo is tested and verified. If
this repo keeps that list somewhere else, `--checks <path>` inlines that file
instead.

The script prints two lines: the markdown file the review was saved to
(under `.droid-reviews/`, which ignores itself in git) and the droid **session
id**. Keep the
session id. A review takes a few minutes; run the script with a long timeout
or in the background. Default model is `glm` (`glm-5.3-flash`, at droid's
default effort); `DROID_REVIEW_MODEL` / `DROID_REVIEW_EFFORT` override.

Non-zero exit means droid did not finish (auth, unknown model, network) —
report the stderr text to the user rather than reviewing nothing.

While it runs, droid's progress streams into a `.log` beside the review file
(the script prints `live log: <path>` on stderr): one line per tool call with
elapsed time, turn, tool and target. `tail` it to see what the reviewer is doing.

**How fresh is a review.** Each run also writes a `.json` of the same name, and
the review file's header says the same in words: when it started and finished,
the branch and commit (`head`) it reviewed, the base and merge-base, and how
many staged / unstaged / untracked files were uncommitted. `status` is
`running` while it goes, then `ok`, `failed` or `interrupted`. Before triaging
a review you did not just run, compare its `head` with `git rev-parse HEAD`
and its uncommitted counts with `git status`: commits or changes since then can
have fixed a finding or made it stale, so say which.

### Several models at once

When the user asks for more than one reviewer (`/droid-review gemini,luna,grok`
or "review it on glm and gemini"), fan out in one command:

```bash
.claude/skills/droid-review/droid-review.sh --models glm,gemini,grok "<focus>"
.claude/skills/droid-review/droid-review.sh "glm,gemini,grok <focus>"   # same, from $ARGUMENTS
```

Each model runs in parallel at its shortcut's default effort (`--effort` applies
to all). `--models` alone still lists the shortcuts. Do not put a model word in
the focus as well; the script refuses that. Run it in the background: stderr
has one line per state change (started + log path, a new turn at most every
30s per model, `ok`/`FAILED` with the result path); read that output to follow
along, and `tail` a model's `.log` for detail. stdout ends with one
`model<TAB>status<TAB>path<TAB>session` line per model, then the index file
(`.droid-reviews/<stamp>-<branch>-multi.md`, a table of every run). Exit 0 when
at least one model finished; relay each failure's line. Triage each review as
below, merging findings several reviewers agree on into one verdict (note who
raised it). A re-check is per model: `--session <that model's id>`, not `last`.

## 2. Triage — every finding gets a verdict

Read the file. For **each** finding, open the code it names and decide:

- **Confirmed** — you reproduced the reasoning (or a test) and it is a real
  defect in the branch's changes.
- **Pre-existing** — real, but not introduced by this branch. Say so; do not
  fix unless trivial and adjacent.
- **False positive** — the reviewer misread the code. Say what it missed, in
  one sentence, so the user can trust the verdict.
- **Nit / style** — real but cosmetic. Fix only if a one-liner.

Never take a finding on faith: the reviewer is a different model with no
knowledge of this repo's conventions (they are in AGENTS.md / CLAUDE.md). A
confident-sounding finding that contradicts a documented convention is usually
the false positive.

## 3. Fix the confirmed ones

Fix confirmed findings, then run the checks that cover them — the repo's own
instructions file says which those are and what each costs. Do not commit
unless the user's standing instruction for the branch says to.

## 4. Re-check with the same reviewer

```bash
.claude/skills/droid-review/droid-review.sh --session <id>
.claude/skills/droid-review/droid-review.sh --session last   # newest review's session
```

`last` reads the id from the newest file under `.droid-reviews/`, so the
re-check works even when the id has fallen out of the conversation (a
compaction, a new day).

This continues the droid session on the model and effort that wrote the
review (read from the review file's header), so the reviewer that raised a
finding is the one that grades the fix. It re-reads its own findings against
the fixed code (the review file's title and `round` say which round it is) and reports fixed / still open / false positive plus anything
new. Do not name a model on a re-check unless the user asks for a different
reviewer. One round trip is enough; do not loop until the reviewer is silent.

## 5. Report

A short table: finding → verdict → what you did. Then the re-check result in
one line. Quote the review file path so the user can read the raw review.
