# droid-review

A second-opinion loop: ask [Factory's `droid` CLI](https://docs.factory.ai/droid-cli/quickstart)
to look at your branch non-interactively, have your main coding agent triage
what comes back against the actual code, fix what's real, then re-check with
the same droid session so it tells you what's fixed, what's still open, and
what's new.

No copy-pasting a review between two chat windows. One command runs the loop.

Two skills, because there are two different things to ask for:

| | |
|---|---|
| **`/droid-review`** | droid's own `/review` — a structured code review: severity, file:line, the scenario that breaks. Triage is confirmed / pre-existing / false positive / nit, then fix and re-check. |
| **`/droid-feedback`** | anything else, in your own words — the copy, the API shape, "is this approach sane". Prose back, no imposed format. Triage separates fact from taste, and taste stays yours. |

## When to use it

Near merge, on a branch you believe is code complete — the point where you'd
otherwise open a PR and hope someone reads it.

What makes it worth the round trip is that the reviewer is *different in two
ways at once*: a different model, running in a different harness, with none of
your session's context or its assumptions. In practice that catches real bugs
in code written by strong models — Fable, GPT-5.6 Sol — because the reviewer
isn't invested in the plan that produced them and has to rediscover the intent
from the diff.

Both are human-invoked by design. The skills tell your agent not to run them on
its own initiative.

## No config files

The one thing droid needs from your repo is *how to check things* — the tests,
the linter, the typechecker, the e2e suite, whatever drives the app. It gets
that from **AGENTS.md / CLAUDE.md**, which droid loads by itself, and the prompt
tells it to go read it.

So there's nothing to install per repo. If your instructions file doesn't
document how to verify the project, that's worth fixing for every agent that
touches it, not just this one — a table of *command → what it proves → what it
costs* is the single highest-leverage thing in an AGENTS.md, because it's the
difference between a reviewer that runs your tests and one that guesses from
the diff.

If that list genuinely lives elsewhere in your repo, point at it:

```bash
droid-review.sh --checks docs/testing.md
```

## What it does in your repo

The reviewer runs at droid's `--auto medium`, which means that inside your repo
it can run your build and test suites, install packages, make network requests,
and commit locally. That's deliberate — a finding backed by a check it actually
ran beats one read off the diff. The script removes droid's `ApplyPatch` tool so
it can't edit your files, and the prompt tells it not to commit.

If that's more autonomy than you want, drop `--auto medium` from the
`DROID_ARGS` array in the script; droid then runs read-only and reviews from the
diff alone.

Tested against droid CLI 0.213.0. droid ignores unknown flags silently, so on a
much newer version, confirm the tool guard still bites:

```bash
droid exec --auto medium --remove-tools ApplyPatch --list-tools   # ApplyPatch: blocked override
```

## Requirements

- **The `droid` CLI**, installed and authenticated: <https://docs.factory.ai/droid-cli/quickstart>.
  You need a Factory account with access to a model — the script defaults to
  `glm-5.3-flash`, but any model your plan can run works (`--model`).
- **git** and **python3** (the script parses droid's JSON output with it).
- **A primary coding agent with its own subscription** to do the triage/fix
  step. This repo packages that step as two
  [Claude Code skills](https://docs.claude.com/en/docs/claude-code/skills).

A run takes anywhere from ~40s to ~8 minutes depending on model, branch size,
and how many checks it decides to run, and it bills against your Factory plan.
Run it with a long timeout or in the background.

## Install

Install both skills together — `droid-feedback` is a thin wrapper around the
script in `droid-review`, so they share one implementation and can't drift
apart.

Per project:

```bash
mkdir -p .claude/skills
cp -r skills/droid-review skills/droid-feedback .claude/skills/
echo '.droid-reviews/' >> .gitignore
```

Or globally, for every project at once:

```bash
mkdir -p ~/.claude/skills
cp -r skills/droid-review skills/droid-feedback ~/.claude/skills/
```

Start a new Claude Code session and run:

```
/droid-review
/droid-review the auth changes
/droid-feedback review the user-facing copy: clarity, one name per concept, voice
```

Claude reads the SKILL.md, runs the script, triages what comes back, applies
what's real, and re-checks with the same droid session.

### Other agents

The loop is a bash script plus two markdown playbooks, so nothing here is
Claude-specific except the packaging. For Codex, Gemini CLI, or anything else:
drop `skills/` in the repo, point the agent at the SKILL.md files, and ask it to
run the loop — adapting the paths and the invocation is a small enough job that
the agent can do it for you.

## Just the script

`skills/droid-review/droid-review.sh` runs standalone from any shell:

```bash
droid-review.sh                          # /review, branch vs. detected default branch
droid-review.sh "the payment retry logic" # same, with something to weight
droid-review.sh --feedback "<ask>"        # plain-words feedback instead of /review
droid-review.sh --uncommitted
droid-review.sh --base origin/main --effort max
droid-review.sh --checks docs/testing.md
droid-review.sh --session last "re-check the fixes in HEAD"
droid-review.sh --help
```

The positional argument is what you're asking droid for this time: emphasis on
top of `/review`, the whole ask under `--feedback`, or the re-check instruction
with `--session`. `DROID_REVIEW_BASE`, `DROID_REVIEW_MODEL` and
`DROID_REVIEW_EFFORT` set the defaults.

It prints the file it saved to and the droid session id; paste both into
whatever you're using to do the triage.

## License

MIT — see [LICENSE](LICENSE).
