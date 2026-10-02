# droid-review

Ask [Factory's `droid` CLI](https://docs.factory.ai/droid-cli/quickstart) to review your branch in the background, and give that feedback to your main coding agent to triage. Your main agent should fix what needs fixing, and then request a follow up review which should be fast to complete.

I do not believe that harnesses and models can effectively code-review themselves. This is because I believe they have the same approach to the tasks at hand, and so they will step through the problems and "think" about them in a similar way as the agent that wrote the code. *Therefore I believe that the best way to get an agentic code review and second-opinon is by using a different harness + different model.*

For your main coding agent AND your backup/review agent, you will want harness (Claude Code / Droid) and model (Opus, Fable / GLM, Gemini) combinations that are made by smart people that are competitive and care a lot about doing a good job. I believe my stack of CC Opus 5.5 + Droid w/ GLM 5.3 Flash/Gemini 3.8 Flash satisfies this requirement 

### Usage

```sh
/droid-review
# Or with options
/droid-review [glm|gemini|luna|auto|fable|opus|astra|sol|grok|qwen|kimi|deepseek] [effort] [focus]
```

What happens:
- Your main agent (e.g. Claude) invokes the skill
- It will request `droid` to do a review in the background, and await the results
- It will receive the code review results within a couple minutes
- It will triage (prioritize, accept, reject) each point of feedback
- Your main agent will do the fixes and then request re-review from the same droid session, which re-uses the session cache resulting in a fast re-review (generally under 30-60 seconds)
- Done. 

Benefits:
- Review was solicited from a different coding harness and model resulting in a true second opinion
    - In my experience, GLM (5.2 and now 5.3 Flash) have been able to find issues in Claude Code's best models, and serve as nice secondary opinions. 
- Time
- No copy-pasting a review between two chat windows. One command runs the loop
- Easy to do on mobile
- Easy to enable automatically via `CLAUDE.md` and/or your prompt (e.g. "Fix this bug and solicit /droid-review") — so your agent will go off for longer, and come back with work that you can be more confident in
- In the short and long run I believe that only agents and verification tests will be able to review code correctness. Human review has a place, but the first step is automation (tests, guardrails) and further leveraging agentic coding skills (`/droid-review` skill, using different harness+model to get a review)

### The Skills

| | |
|---|---|
| **`/droid-review`** | wraps droid's own `/review` skill. Receive a structured code review: severity, file:line, the scenario that breaks. Triage is confirmed / pre-existing / false positive / nit, then fix and re-check. |
| **`/droid-feedback`** | an open-ended prompt, literally ask for feedback like "is this approach sane?". Receive prose back, no imposed format. Use when you want feedback, not code review |

### When to use it

Near merge, on a branch you believe is code complete

### How to get the most out of it

The one thing `droid` needs from your repo is *how to check things* — the tests, the linter, the typechecker, the e2e suite, whatever drives the app.

The best way to provide this info is in **AGENTS.md / CLAUDE.md**, which droid always loads. In general it is good practice to list out your verification layer here; it helps humans and it helps agents

If the instructions for verification live somewhere else in your repo, point at it. This will help with efficiency rather than leaving it up to `droid` to figure it out

```bash
droid-review.sh --checks docs/testing.md
```

### What droid does in your repo

- The reviewer runs at droid's `--auto medium`, which means that inside your repo
it can run your build and test suites, install packages, make network requests,
and commit locally. 
- This is deliberate, finding should be backed by checks, and not just reading the diff
- The script removes droid's `ApplyPatch` tool so it can't edit your files, and the prompt tells it not to commit
- If that's more autonomy than you want, drop `--auto medium` from the `DROID_ARGS` array in the script; droid then runs read-only and reviews from the diff alone. Not recommended, but the option is there for you

### Requirements

- **The `droid` CLI**, installed and authenticated: <https://docs.factory.ai/droid-cli/quickstart>.
  You need a Factory account with access to a model — the script defaults to
  `glm-5.3-flash`, but any model your plan can run works (`--model`).
- **git** and **python3** (the script parses droid's JSON output with it)
- **A primary coding agent with its own subscription** to do the triage/fix step. This is generally the same agent that did the implementation. I recommend [Claude Code]( https://claude.ai/ ) but alternatives like Cursor, Codex, Pi, etc. work too

A run takes anywhere from ~40s to ~8 minutes depending on model, branch size, and how many checks it decides to run, and it bills against your Factory plan. Your agent should run it in the background automatically. It should be run in the background, or at minimum with a large timeout.

### Install

Install both skills together — `droid-feedback` is a thin wrapper around the script in `droid-review`, so they share one implementation and can't drift apart. Have your main coding agent help you with this, they are great at this sort of task!

The usual way: clone this repo and link both skills into your personal skills
folder, so a `git pull` here updates every project:

```bash
git clone https://github.com/AuthorOfTheSurf/droid-review-skill
cd droid-review-skill
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/droid-review" "$PWD/skills/droid-feedback" ~/.claude/skills/
```

Run `git pull` in the clone now and then to pick up new model shortcuts. To
remove it, delete the two links.

Or copy them into one project (a copy never updates):

```bash
mkdir -p .claude/skills
cp -r path/to/droid-review-skill/skills/droid-review path/to/droid-review-skill/skills/droid-feedback .claude/skills/
```

Reviews land in `.droid-reviews/` in whichever repo you run from. The folder
ignores itself (the script puts a `.gitignore` of `*` in it), so no repo needs
a line for it.

Usually you will need to restart your `claude` in order to pick up new skills. After restart you should see `/droid-review` and `/droid-feedback` autocomplete and be available

### Model shortcuts

- First parameter allows optional specification of a model, e.g. (glm = GLM 5.3 Flash)
- Second parameter is an effort level, overriding droid's default for that one run (`/droid-review luna max`)
- Anything else is the focus, so `/droid-review the gemini integration` is a GLM review about Gemini

| Shortcut | Model | droid's default effort | Levels it takes |
|---|---|---|---|
| `glm` (default) | `glm-5.3-flash` | high | low, high, max |
| `gemini` | `gemini-3.8-flash` | high | low, medium, high |
| `luna` | `gpt-6-luna` | medium | none … max |
| `auto` | `auto` | none (droid picks) | — |
| `fable` | `claude-fable-5.1` | high | off … max |
| `opus` | `claude-opus-5-5` | medium | low … max |
| `astra` | `gpt-6-astra` | medium | low … max |
| `sol` | `gpt-6.1-sol` | medium | low … max |
| `grok` | `grok-4.7` | high | low … xhigh |
| `qwen` | `qwen3.8-max` | xhigh | low, medium, xhigh |
| `kimi` | `kimi-k3` | high | off, low, high, max |
| `deepseek` | `deepseek-v4.1-flash` | high | off, low, high, max |

No shortcut pins an effort: each runs at droid's default for that model, and
a higher level is opt-in for the run you name it on (`/droid-review luna max`).
A max-effort review can take half an hour.

Any other model id droid accepts works as the first word too (`droid exec -m x
--list-tools` lists them all; `droid exec --help` lags behind). The script
checks the model before it starts droid, and the effort against the levels
that model supports, so `gemini max` fails at once with the levels Gemini
takes. `droid-review.sh --efforts` prints every model's levels and default
(`--efforts luna` just one) — the same table droid's `/model` picker shows,
read from the droid install, so it covers models `droid exec --help` leaves
out — with each model's price multiplier and whether it is new, on sale or
deprecated. `--whats-new` prints what the top of `/model` shows: new models,
discounts and when they end, deprecated models with droid's replacement, and
whether each shortcut is the newest generation in droid's own family order. The
table lives in `shortcut()` in the script; the family names point at the newest
model as of droid 0.232.0, so move them when droid ships a newer one.

### Just the script

`skills/droid-review/droid-review.sh` runs standalone from any shell:

```bash
droid-review.sh                          # /review, branch vs. detected default branch
droid-review.sh "the payment retry logic" # same, with something to weight
droid-review.sh --feedback "<ask>"        # plain-words feedback instead of /review
droid-review.sh --uncommitted
droid-review.sh "luna the payment retry logic" # a model shortcut first
droid-review.sh --models                 # list the shortcuts
droid-review.sh --efforts luna           # a model's effort levels and default (alone: every model)
droid-review.sh --whats-new              # new, discounted and deprecated models; shortcuts vs. newest
droid-review.sh --models glm,gemini,grok "the auth changes"   # all three, in parallel
droid-review.sh "glm,gemini the auth changes"                 # same fan-out, as the first word
droid-review.sh --base origin/main --effort max
droid-review.sh --checks docs/testing.md
droid-review.sh --session last "re-check the fixes in HEAD"
droid-review.sh --help
```

The positional argument is what you're asking droid for this time: emphasis on
top of `/review`, the whole ask under `--feedback`, or the re-check instruction
with `--session`

A `--session` run keeps the model and effort that wrote the
review, read from the review file's header, unless you name a model.
`DROID_REVIEW_BASE`, `DROID_REVIEW_MODEL` and `DROID_REVIEW_EFFORT` set the
defaults.

It prints the file it saved to and the droid session id; paste both into
whatever you're using to do the triage. While droid works, its progress streams
into a `.log` of the same name (one line per tool call: elapsed, turn, tool,
target), so `tail -f` shows what it is doing.

Each run also writes a `.json` of the same name: its status (`running`, then
`ok`, `failed` or `interrupted`), when it started and finished, the branch,
commit and base it reviewed, and how many files were staged, unstaged and
untracked at the time. The review file's header carries the same facts, so you
(or your agent) can tell how fresh an old review is against the repo now.

**Several models.** `--models a,b,c` (or a comma list as the first word) runs
the same ask on each model in parallel, each at its shortcut's effort. On a
terminal, stderr shows a board redrawn in place, one line per model; elsewhere
(an agent's shell, CI) it prints one line per state change. stdout gets
`model<TAB>status<TAB>path<TAB>session` per model and, last, an index file
`.droid-reviews/<stamp>-<branch>-multi.md` tabling status, time, words, session
and result for each. Exit 0 if any model succeeded; Ctrl-C stops the rest and
keeps what finished. `--models` with no list still prints the shortcuts.

### Live status in Claude Code (optional)

Reviews usually run in the background while you keep working. To see them as
they go, add rows to Claude Code's status line, one per running review, under
the status line you already have:

```
◓ droid · review   · GLM-5.3-Flash     ▓▓▓▓▓▓░░░░  0:25 / ~0:40  turn 3 · Execute npm test
◓ droid · review 2 · Gemini 3.8 Flash  ▓▓░░░░░░░░  0:12 / ~1:30  turn 1 · Read README.md
✓ droid · review   · GPT-6 Luna max    ██████████  done in 2:14 · 21 turns · .droid-reviews/…-gpt-6-luna.md
```

"review 2" is a re-check (`--session`), the second round of that review; the
review file's title and metadata carry the round too. The time after `~` is
the median of that model's earlier finished runs of the same kind (first
review or re-check) in the repo, and the bar fills toward it (amber once past it; a pulse until there is
any history). A finished run stays a minute with a solid bar and its result in bold, then goes. With
nothing running it prints nothing.

It is one script, `skills/droid-review/statusline.py`, set in
`~/.claude/settings.json`. Put the status line command you already have, if
any, after `--`: it runs first, on the same input, and these rows go under it.

```json
"statusLine": {
  "type": "command",
  "command": "python3 /path/to/droid-review-skill/skills/droid-review/statusline.py -- <your current statusLine command>",
  "refreshInterval": 2
}
```

`refreshInterval` re-runs the line every 2 seconds, so the elapsed time moves
while the session is idle. To undo, put your old command back.

### Maintaining it

droid changes under the script without warning: new models, retired ids,
renamed flags, a different help format. In this repo, `/maintain-droid-review-skill`
(a project skill under `.claude/skills/`) checks the script against the
installed droid, proposes shortcut moves for you to pick from, runs every
script path against a stub droid, and keeps the docs in agreement. Run it after
a droid upgrade.

## License

MIT — see [LICENSE](LICENSE).
