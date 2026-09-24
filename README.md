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

*My recommendation*, symlink them from a clone of this repo, so a `git pull` (or an
edit here) reaches every project with nothing to copy:

```bash
mkdir -p ~/.claude/skills
ln -s "$PWD/skills/droid-review" "$PWD/skills/droid-feedback" ~/.claude/skills/
```

Run `git pull` in the clone now and then to pick up new model shortcuts. A copy
made with `cp` never updates.

A global install still writes reviews to `.droid-reviews/` in whichever repo
you run it from, so add that to each repo's `.gitignore` or to your global git
excludes file.

Usually you will need to restart your `claude` in order to pick up new skills. After restart you should see `/droid-review` and `/droid-feedback` autocomplete and be available

### Model shortcuts

- First parameter allows optional specification of a model, e.g. (glm = GLM 5.3 Flash)
- Second parameter is an effort level overrides of the default effort level for one run (`/droid-review luna xhigh`)
- Anything else is the focus, so `/droid-review the gemini integration` is a GLM review about Gemini

| Shortcut | Model | Effort |
|---|---|---|
| `glm` (default) | `glm-5.3-flash` | high |
| `gemini` | `gemini-3.8-flash` | high |
| `luna` | `gpt-6-luna` | max |
| `auto` | `auto` | none (droid picks) |
| `fable` | `claude-fable-5.1` | droid's default |
| `opus` | `claude-opus-5-5` | droid's default |
| `astra` | `gpt-6-astra` | droid's default |
| `sol` | `gpt-6-sol` | droid's default |
| `grok` | `grok-4.7` | droid's default |
| `qwen` | `qwen3.8-max` | droid's default |
| `kimi` | `kimi-k3` | droid's default |
| `deepseek` | `deepseek-v4-pro` | droid's default |

Any other model id droid accepts works as the first word too (`droid exec -m x
--list-tools` lists them all; `droid exec --help` lags behind). The script
checks the model before it starts droid, and the effort against the levels
`droid exec --help` gives for that model, so `gemini max` fails at once with the
levels Gemini takes; a model the help does not list yet runs unchecked. The
table lives in `shortcut()` in the script; the family names point at the newest
model as of droid 0.226.2, so move them when droid ships a newer one.

### Just the script

`skills/droid-review/droid-review.sh` runs standalone from any shell:

```bash
droid-review.sh                          # /review, branch vs. detected default branch
droid-review.sh "the payment retry logic" # same, with something to weight
droid-review.sh --feedback "<ask>"        # plain-words feedback instead of /review
droid-review.sh --uncommitted
droid-review.sh "luna the payment retry logic" # a model shortcut first
droid-review.sh --models                 # list the shortcuts
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
whatever you're using to do the triage.

## License

MIT — see [LICENSE](LICENSE).
