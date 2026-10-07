# droid-review

Get a second-opinion code review of your branch from [Factory's `droid` CLI](https://docs.factory.ai/droid-cli/quickstart), handed straight to your main coding agent to triage, fix, and re-check.

Models and harnesses should not review their own code. They tend to share blind spots, follow the same reasoning patterns, and evaluate problems the way they did when they wrote the code. The strongest agentic review pairs a different coding harness with a different model family, and backs its findings by running the repository's own checks, not by reading the diff alone.

## Skills

| | |
|---|---|
| `/droid-review` | Structured code review: severity, `file:line`, the scenario that breaks. Your agent triages each finding, fixes, and asks for a re-check. |
| `/droid-feedback` | An open-ended ask ("is this approach sane?"). Prose back, no imposed format. |
| `/droid-history` | This branch's reviews with their re-check rounds, the commit each reviewed, and what was done about it. Runs no model. |

## Usage

```sh
/droid-review
/droid-review [model] [effort] [focus]   # e.g. /droid-review gemini high the auth changes
```

1. Your agent starts `droid` in the background and waits (about 40 seconds to 8 minutes).
2. It triages each finding: confirmed, pre-existing, false positive, or nit.
3. It fixes what needs fixing and records a one-line note.
4. It asks the same droid session to re-check. The session is reused, so the re-check is fast.

Use it near merge, on a branch you believe is code complete.

## Requirements

- The `droid` CLI, installed and authenticated, with a Factory plan that can run a model (default `glm-5.3-flash`)
- `git` and `python3`
- A primary coding agent to triage and fix (Claude Code recommended, others work)

Runs bill against your Factory plan.

## Install

```bash
git clone https://github.com/AuthorOfTheSurf/droid-review-skill
cd droid-review-skill
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/droid-review" "$PWD/skills/droid-feedback" "$PWD/skills/droid-history" ~/.claude/skills/
```

Install all three together, because the other two wrap the script in `droid-review`. Then restart `claude`. To update the skills, run `git pull` in the clone. To remove them, delete the links.

## Models

Shortcuts: `glm` (default), `gemini`, `luna`, `auto`, `fable`, `opus`, `sonnet`, `astra`, `sol`, `grok`, `qwen`, `kimi`, `deepseek`. Any other model id droid accepts works too. Each runs at droid's default effort unless you name one.

```bash
droid-review.sh --models                 # list the shortcuts
droid-review.sh --efforts luna           # a model's effort levels and default
droid-review.sh --whats-new              # new, discounted, and deprecated models
droid-review.sh --models glm,gemini,grok "the auth changes"   # several, in parallel
```

## What droid does in your repo

The reviewer runs at `--auto medium`. It can run your builds and tests, install packages, make network requests, and commit locally, so that findings are backed by checks and not only by a reading of the diff. Its file-editing tools are removed and the prompt tells it not to commit. For a read-only review, drop `--auto medium` from `DROID_ARGS` in the script.

Tell droid how to check things: list your tests, linter, and typechecker in `AGENTS.md` or `CLAUDE.md`, or point at them with `--checks docs/testing.md`.

## The script on its own

`skills/droid-review/droid-review.sh` runs from any shell:

```bash
droid-review.sh "the payment retry logic"     # review, with something to weight
droid-review.sh --feedback "<ask>"            # plain-words feedback
droid-review.sh --uncommitted
droid-review.sh --session last "re-check the fixes in HEAD"
droid-review.sh --note last "fixed 2; the race is a false positive"
droid-review.sh --history                     # --all: every branch
droid-review.sh --compare                     # is the newest review still current?
droid-review.sh --help                        # every flag
```

Reviews, logs, and run metadata land in `.droid-reviews/`, which ignores itself in git. To watch a run, `tail -f` its log. `--compare` sets a review against the repo now: what changed since, and whether this branch touched each cited line or the line was already there.

## Live status in Claude Code (optional)

A band above the prompt shows one row per running review: progress against that model's usual time, what droid is doing, and what came of it. The band needs a Claude Code that loads mods (early access).

```bash
ln -s "$PWD/skills/droid-reviews" ~/.claude/skills/
```

## Maintaining

droid's models and flags change without warning. In this repo, `/maintain-droid-review-skill` checks the script against the installed droid and runs every path against a stub. See `AGENTS.md` for the verification suite.

## License

MIT. See [LICENSE](LICENSE).
