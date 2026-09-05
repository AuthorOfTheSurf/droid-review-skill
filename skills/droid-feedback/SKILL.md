---
name: droid-feedback
description: Ask Factory's droid for a second opinion on the branch in plain words — the copy, the API shape, a design question, anything that is not a structured code review — then weigh what comes back and apply only what the user picks. Human-invoked; run only when the user asks for droid feedback, never on your own initiative. For a structured code review, use droid-review instead.
---

# droid feedback → weigh → propose → re-check

Same loop as droid-review, different ask. `droid-review` runs droid's `/review`,
which is a code review and reports like one. This skill sends droid whatever
the user actually wants looked at, in their words, and gets prose back.

Reach for it when the question is not "what's broken": the user-facing copy, a
naming pass, whether an approach is sound, whether a doc matches the code, how
an API would read to someone who did not write it.

**Where the script is.** `droid-feedback.sh` sits next to this file and is a
thin wrapper — the implementation lives in the **droid-review** skill folder
beside it, so the two commands cannot drift. Both must be installed.

## 1. Ask

```bash
.claude/skills/droid-feedback/droid-feedback.sh "<the user's ask, in their words>"
.claude/skills/droid-feedback/droid-feedback.sh --uncommitted "<ask>"
.claude/skills/droid-feedback/droid-feedback.sh --model gemini-3.8-flash "<ask>"
```

The ask is required and carries the whole framing — what to look at, what
counts, and how to report it. Pass the user's `$ARGUMENTS` through as-is where
you can; sharpen it only where it is genuinely ambiguous, and say that you did.
A vague ask gets vague prose back, so it is worth a sentence of specifics:

```bash
droid-feedback.sh "Review the user-facing copy, not the code: every string a
user reads or a screen reader speaks. Judge clarity to a first-time user,
brevity for the space it sits in, one consistent name per concept across
screens, consistent voice and casing, and labels that read well spoken. Report
each as file:line, the current string, a proposed string, one line of why, and
a confidence. Group by screen, and end with a Terms section listing any concept
named more than one way."
```

**Pick the model for the job.** The user runs different reviews on different
models — `--model gemini-3.8-flash` for language and copy work, the default
`glm-5.3-flash` for code-shaped questions. Ask if it matters and they have not
said.

The script prints the saved markdown file and the droid **session id**; keep
the id. Everything droid-review's script accepts works here too (`--base`,
`--uncommitted`, `--effort`, `--checks`, `--session`); `--help` prints them.

## 2. Weigh what comes back — do not just apply it

This is the part that differs from a code review. Feedback is mostly
*proposals*, and the taste is the user's, not droid's and not yours.

- **Factual** — a broken link, a term used two ways, a label that contradicts
  what the button does, a doc that no longer matches the code. Verify it
  against the repo, then fix it; these are the ones you may apply directly.
- **Judgement** — a rewording, a renaming, a structural suggestion. Present it;
  do not apply it. The voice is the user's.
- **Wrong** — droid missed context. Say what it missed in one sentence.

Present the judgement calls as a table: current / proposed / your take. Then
apply only what the user picks, plus the factual fixes. If the ask was itself
about taste, expect the whole review to land in this column, and do not let its
length pressure you into applying it wholesale.

## 3. Re-check (optional)

```bash
.claude/skills/droid-feedback/droid-feedback.sh --session last
```

Worth it when you applied a batch and want the same reviewer to confirm the
terms are now consistent. Skip it when the user only took one or two
suggestions — there is nothing to re-check.

## 4. Report

The table from step 2, what you applied, and the file path so the user can read
droid's raw prose. If you sharpened the user's ask before sending it, quote the
version you actually sent.
