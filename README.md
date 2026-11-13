# droid-review

Get a second-opinion code review of your branch from [Factory's `droid` CLI](https://docs.factory.ai/droid-cli/quickstart), handed straight to your main coding agent to triage, fix, and re-check.

Models and harnesses should not review their own code. They tend to share blind spots, follow the same reasoning patterns, and evaluate problems the way they did when they wrote the code. The strongest agentic review pairs a different coding harness + different model family. This is supported by running the repository's own checks—not by reading the diff alone.

Benefits: Ship features & fixes with greater confidence. Solicit review from multiple models while only paying for one additional subscription.

## Skills

| | |
|---|---|
| `/droid-review` | Structured code review: severity, `file:line`, the scenario that breaks. Your agent triages each finding, fixes, and asks for a re-check. |
| `/droid-feedback` | Any ask, sent as you wrote it ("is this approach sane?"). Prose back, no imposed format, no checks unless asked. |
| `/droid-history` | This branch's reviews with their re-check rounds, the commit each reviewed, and what was done about it. Runs no model. |
| `/maintain-droid-review-skill` | Used by maintainers to update these skills with respect to `droid` updates e.g. new models added. |

## Usage

```sh
# Uses droid's review skill and the default model (GLM-5.3-flash) to code-review your branch
/droid-review

# Optional parameters. I mainly specify model shortcuts
/droid-review [model] [effort] [focus]

# Review with Gemini (gemini-3.8-flash) on high effort
/droid-review gemini high

# Review with multiple models in parallel
/droid-review glm,luna,muse

# Request feedback on copywriting with a specific model
/droid-feedback sol review the copy on the front page

# Research with multiple models
/droid-feedback grok,qwen,luna-fast What are competitors doing? Any cool features we should consider adding?

# Just plain prose prompt, your agent will use the skills. Great when developing off your phone on mobile
When you're done please request droid-review with glm and luna-fast, and then feel free to merge it if it looks good. ty
```

1. Your agent starts `droid` in the background and waits (about 2–10+ minutes, depends on your codebase and the model).
2. Your agent triages each finding: confirmed, pre-existing, false positive, or nit.
3. Your agent fixes what needs fixing and records a one-line note.
4. Your agent asks the same droid session to re-check. The session is reused, so the re-check is fast (30-120s).

Use it near merge, on a branch you believe is code complete.

## Requirements

- A primary coding agent to run the skills and to do the triage and fixes (Claude Code recommended, others work)
- The `droid` CLI, installed and authenticated, with a Factory plan that can run a model (default `glm-5.3-flash`)
- `git` and `python3`

Runs bill against your Factory plan.

## Install

_Easiest way_: Just link your agent to the repo and tell it to install the skill

```bash
git clone https://github.com/AuthorOfTheSurf/droid-review-skill
cd droid-review-skill
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/droid-review" "$PWD/skills/droid-feedback" "$PWD/skills/droid-history" ~/.claude/skills/
```

Install all three together, because the other two wrap the script in `droid-review`. Then restart `claude`. To update the skills, run `git pull` in the clone. To remove them, delete the links. Use your main agent to do these things for you

## Models

Shortcuts: `glm` (default), `gemini`, `luna`, `auto`, `fable`, `opus`, `sonnet`, `astra`, `sol`, `grok`, `qwen`, `kimi`, `deepseek`, `argon`, `muse`, `nemotron`, `haiku`, `luna-fast`, `beam`, `carbon`, `hydrogen`. Any other model id droid accepts works too. Each runs at droid's default effort unless you name one. Maintainers bump the versions of these shortcuts periodically.

```bash
droid-review.sh --models                 # list the shortcuts
droid-review.sh --efforts luna           # a model's effort levels and default
droid-review.sh --whats-new              # new, discounted, and deprecated models
droid-review.sh --models glm,gemini,grok "the auth changes"   # several, in parallel
```

## What droid does in your repo

The reviewer runs at `--auto medium`. It can run your builds and tests, install packages, make network requests, and commit locally, so that findings are backed by checks and not only by a reading of the diff. Its file-editing tools are removed and the prompt tells it not to commit. For a read-only review, drop `--auto medium` from `DROID_ARGS` in the script.

Tell droid how to check things: list your tests, linter, and typechecker in `AGENTS.md` or `CLAUDE.md`, or point at them with `--checks docs/testing.md`.

## Install progress bars in Claude Code

```bash
ln -s "$PWD/skills/droid-reviews" ~/.claude/skills/
```

One bar per running review showing progress against that model's usual time, what droid is doing, and what came of it. The band needs a Claude Code that loads Claude code "mods". Optional but recommended—it's more fun and looks pretty.

<img width="1528" height="365" alt="SCR-20261102-mlyp" src="https://github.com/user-attachments/assets/1f2c424c-9f54-4c96-9152-16e4c56218bb" />



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

## Maintaining

- Update droid via `droid update`
- Run `/maintain-droid-review-skill` which will check the script against the installed droid and runs every path against a stub. It will suggest models to bump, and note new models that don't have shortcuts yet

## License

MIT. See [LICENSE](LICENSE).
