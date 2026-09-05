---
name: droid-review
description: Second-opinion review of the current branch from Factory's droid (GLM by default, any droid model), triaged against the code, fixed, and re-checked. Code review by default; --rubric copy.md reviews the app's user-facing copy instead. Human-invoked, near merge — run only when the user asks for a droid review or to triage one, never on your own initiative.
---

# droid review → triage → fix → re-check

The loop the user used to run by hand (droid tab → `/review` → paste into
Claude → "please triage this") is one command now. You run it end to end.

## 1. Get the review

```bash
.claude/skills/droid-review/droid-review.sh              # branch vs the default branch
.claude/skills/droid-review/droid-review.sh --uncommitted
.claude/skills/droid-review/droid-review.sh --focus "<what the user cares about>"
```

The script sits next to this file so the skill is one folder to copy between
repos; `checks.md` beside it is the repo-specific list of checks the reviewer
is told to run (edit that for a new repo, or delete it to fall back to the
project's instructions file). The base branch is detected (origin/HEAD, else
main/master); `--base` overrides.

**Other kinds of review.** `--rubric <file>` swaps the code-review prompt
for the file's contents; `copy.md` beside the script reviews the app's
user-facing copy (clarity, one name per concept, voice, paywall tone,
spoken labels). Pass `--model` when the user names one — they use a
different model for different reviews.

```bash
.claude/skills/droid-review/droid-review.sh --rubric copy.md --model gemini-3.8-flash
```

Triage for a copy review is different: a term inconsistency or an unclear
string is a finding to fix; a rewording is a proposal. Do not apply
taste-level rewrites on your own — the voice is the user's. Present them as a
table (current / proposed / your take) and apply only what the user picks,
or what is plainly a consistency fix.

The script prints two lines: the markdown file the review was saved to
(under `.droid-reviews/`, gitignored) and the droid **session id**. Keep the
session id. A review takes a few minutes; run the script with a long timeout
or in the background, and if the user gave `$ARGUMENTS`, pass it as `--focus`
(or `--model` / `--effort` when they name one). Default model is `glm-5.3-flash`
at reasoning `high`; `DROID_REVIEW_MODEL` / `DROID_REVIEW_EFFORT` override.

Non-zero exit means droid did not finish (auth, unknown model, network) —
report the stderr text to the user rather than reviewing nothing.

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
knowledge of this repo's conventions (see the project's instructions file —
AGENTS.md / CLAUDE.md — for what those are). A confident-sounding finding that
contradicts a documented convention is usually the false positive.

## 3. Fix the confirmed ones

Fix confirmed findings, then run the checks that cover them — see `checks.md`
next to this file for this repo's list, or fall back to the project's
instructions file if there is no `checks.md`. Do not commit unless the user's
standing instruction for the branch says to.

## 4. Re-check with the same reviewer

```bash
.claude/skills/droid-review/droid-review.sh --session <id>
.claude/skills/droid-review/droid-review.sh --session last   # newest review's session
```

`last` reads the id from the newest file under `.droid-reviews/`, so the
re-check works even when the id has fallen out of the conversation (a
compaction, a new day).

This continues the droid session so it re-reads its own findings against the
fixed code and reports fixed / still open / false positive plus anything new.
One round trip is enough; do not loop until the reviewer is silent.

## 5. Report

A short table: finding → verdict → what you did. Then the re-check result in
one line. Quote the review file path so the user can read the raw review.
