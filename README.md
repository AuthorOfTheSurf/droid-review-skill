# droid-review

A second-opinion code review loop: ask [Factory's `droid` CLI](https://docs.factory.ai/droid-cli/quickstart)
to review your branch non-interactively, have your main coding agent triage
every finding against the actual code (confirmed / pre-existing / false
positive / nit), fix the confirmed ones, then re-check with the same droid
session so it tells you what's fixed, what's still open, and what's new.

No copy-pasting a review between two chat windows. One command runs the whole
loop.

## How it works

- `skill/droid-review.sh` — a plain bash script. It shells out to `droid exec`,
  builds the right prompt for the scope you asked for (branch vs. base,
  uncommitted changes, a focus area, a different rubric entirely), and saves
  the review as markdown under `.droid-reviews/` (gitignore that in your
  project). It has no dependency on any particular coding agent.
- `skill/SKILL.md` — the triage playbook, written as a
  [Claude Code skill](https://docs.claude.com/en/docs/claude-code/skills) (the
  frontmatter + instructions format Claude Code loads from
  `.claude/skills/<name>/SKILL.md`). If you're driving this with something
  other than Claude Code, read it anyway — it's the instructions for the
  human/agent doing the triage step, framework aside.
- `skill/checks.md` — a template listing *this repo's* cheap-to-expensive
  checks, so the reviewer runs real commands instead of reasoning off the
  diff alone. Edit it per project.
- `skill/copy.md` — an optional rubric that swaps the code review for a
  user-facing copy review (clarity, consistent terminology, tone, a11y
  labels). Pass `--rubric copy.md` to use it.
- `examples/tworduel/` — a real `checks.md` and `copy.md` from the project
  this was built in, so you can see what a filled-in version looks like.

## Requirements

- **The `droid` CLI**, installed and authenticated: <https://docs.factory.ai/droid-cli/quickstart>.
  You need a Factory account/subscription with access to a model — the script
  defaults to `glm-5.3-flash`, but any model your Factory plan can run works
  (`--model`).
- **A primary coding agent with its own subscription** to do the triage/fix
  step — read the review, decide what's real, fix it, ask droid to re-check.
  This repo packages that step as a Claude Code skill, but the mechanism
  (a bash script + a markdown playbook) works with any agent; see below.

## Install

### Claude Code

Copy the `skill/` folder into your project (or `~/.claude/skills/` for a
global install) as `droid-review`:

```bash
cp -r skill .claude/skills/droid-review
```

Restart Claude Code (or start a new session) and run:

```
/droid-review
/droid-review --focus "the auth changes"
/droid-review --rubric copy.md
```

Claude reads `SKILL.md`, runs `droid-review.sh`, triages the findings, fixes
what's confirmed, and re-checks with the same droid session.

### Codex

Codex doesn't have a "skill" format the same way, but the loop itself doesn't
need one — it's a script plus a playbook.

1. Drop `skill/droid-review.sh` and `skill/checks.md` somewhere in your repo
   (e.g. `.codex/droid-review/`), and edit `checks.md` for your project.
2. Add a custom prompt in `~/.codex/prompts/droid-review.md` (or paste
   `skill/SKILL.md`'s steps straight into your `AGENTS.md`) so Codex knows the
   loop: run the script, read the output file, triage each finding, fix
   confirmed ones, re-check with `--session last`.
3. Invoke it by asking Codex to run that prompt, or just say "run a droid
   review and triage it" — Codex can follow the steps in `AGENTS.md` directly.

### Gemini CLI / Antigravity

Same shape as Codex: no native skill loader, but the same two ingredients
work.

1. Drop `skill/droid-review.sh` and `skill/checks.md` into the repo and edit
   `checks.md`.
2. Point Gemini at `skill/SKILL.md` as instructions — either as a custom
   command if your Gemini setup supports one, or by including it in your
   project's context file so the agent picks up the triage steps.
3. Ask it to run the script and triage the output the same way.

### Just the script, no agent packaging

`skill/droid-review.sh` runs standalone from any shell:

```bash
skill/droid-review.sh                      # branch vs. detected default branch
skill/droid-review.sh --uncommitted
skill/droid-review.sh --focus "the payment retry logic"
skill/droid-review.sh --rubric skill/copy.md --model gemini-3.8-flash
skill/droid-review.sh --session last "re-check the fixes in HEAD"
```

It prints the review's file path and the droid session id; paste both into
whatever you're using to do the triage.

## License

MIT — see [LICENSE](LICENSE).
