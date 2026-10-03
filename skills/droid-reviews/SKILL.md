---
name: droid-reviews
description: Show the droid reviews run in this repo as a history — each review with its re-check rounds, when they ran, how they ended, the commit each reviewed and how far HEAD has moved since, and what was done about each. Human-invoked; run when the user asks what droid reviews exist, when one last ran, or how current a review is.
argument-hint: "[all]"
---

# droid reviews: the history

Prints what `.droid-reviews/` holds for this branch, newest first. Read-only:
it runs no model and changes nothing.

**Where the script is.** `droid-reviews.sh` sits next to this file and is a
thin wrapper; the implementation lives in the **droid-review** skill folder
beside it, so both must be installed. The path is
`.claude/skills/droid-reviews/droid-reviews.sh` for a project install and
`~/.claude/skills/droid-reviews/droid-reviews.sh` for a global one. Use
whichever directory this SKILL.md was loaded from.

```bash
.claude/skills/droid-reviews/droid-reviews.sh        # this branch
.claude/skills/droid-reviews/droid-reviews.sh all    # every branch
```

Pass `all` through when the user gave it.

**Show the output as it is**, in a code block: it is laid out to be read.
Do not re-table or summarize it. After it, add at most two lines, and only
when they help: a review whose commit HEAD has moved far past (its findings
may be stale), a round still running, or a review with no `→` line that you
triaged in this conversation and can note now with
`droid-review.sh --note <review> "<what was done>"`.

How to read it: one block per droid session, a review with its re-checks
(rounds 1, 2, …). Each round shows when it ran, how it ended (ok in, failed
after, interrupted, running, stopped), the commit it reviewed with `current`
or how many commits behind HEAD it is. A `→` line is the
note the agent that triaged the round left on it: what it did about the
review, in its own words, not something the history verified.
