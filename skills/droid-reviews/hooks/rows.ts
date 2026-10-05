// What a row says, worked out from what droid-review.sh writes to
// .droid-reviews/: each run's .json (status, model, round, start, pid) and the
// end of its .log (the turn and the tool calls droid has made). Nothing here
// reads a file or the clock: register.tsx does, and hands the result in.
//
//   ⠹ droid-review · GLM-5.3-Flash                ⠹ 25s / ~40s                 reading files · turn 3 · Read src/auth.ts
//   ⠹ droid-review · Gemini 3.8 Flash (round 2)   ⠹ 4m 12s / ~1m 30s           running checks for 50s · turn 9 · Execute npm test
//   ✓ droid-feedback · GPT-6 Luna max             ✓ 2m 14s · 21 turns          awaiting triage for 3m...
//
// After the dot comes the model, with the effort if one was named; "(round 2)"
// is a re-check (--session), the second round.
//
// The bar is one piece: its text sits inside it and its ground fills from the
// left as time passes, measured against the median time of this model's
// finished runs of the same kind (review or feedback, first round or re-check)
// in the same folder. A re-check takes a fraction of a first review, and
// feedback as long as its ask, so each is timed against its own kind. The bar
// reaches four fifths at that estimate and stops there, still blue, however
// late the run is: how much is left is not known, and the open fifth says so.
// Only a finished run fills the bar: the same bar then holds the result.
// Without any history a block drifts across it instead.
//
// After the bar comes what droid is doing, worked out from the kinds of tool it
// called in its last three turns, not from what the calls said: reading files
// (Read, Grep, Glob, LS, and commands that only look, such as git diff),
// running checks (any other command), researching (WebSearch, FetchUrl),
// planning (TodoWrite), working (any other tool), and thinking when nothing has
// been logged for half a minute, since droid logs tool calls and neither its
// reasoning nor the writing of its answer. The log does say when a command
// comes back, so a check still going after half a minute stays "running
// checks" and one that has returned does not. Either way the row then says for
// how long.
//
// A finished run keeps its row a while: its result, and what has come of it,
// "awaiting triage for 3m...", then "triaged 2m ago:" and the note the triaging
// agent left (droid-review.sh --note).

import type { DroidReviewsRow, DroidReviewsSeg } from '../types'

export type Meta = {
  status?: string
  kind?: string | null
  model?: string | null
  model_name?: string | null
  effort?: string | null
  round?: number | null
  started?: string | null
  finished?: string | null
  duration_s?: number | null
  turns?: number | null
  error?: string | null
  pid?: number | string | null
  responses?: unknown
}

/** One run as register.tsx read it. */
export type Run = {
  name: string
  meta: Meta
  /** When its log was last written, in seconds; null when it has none. */
  logAt: number | null
  /** Whether its process is there; asked only of a run its .json calls running. */
  isAlive: boolean
  /** The end of its log, whole lines; read only for a running run. */
  lines: string[]
}

/** The first and last line of a log that has no .json: a run older than the metadata. */
export type LogEnds = { first: string; last: string }

export type History = Map<string, number[]>

export const SHOW_FINISHED_S = 900 // a finished row stays this long after the last thing that happened to it
export const SHOW_UNTRIAGED_S = 3600 // and one nobody has said anything about yet, this long
// A run killed outright (SIGKILL, a reboot) never records its end, and its pid
// can be reused; a log silent this long means it is not running any more.
export const STALE_S = 3600
export const QUIET_S = 30 // nothing logged this long: droid is thinking, or a command is still going
const RECENT_TURNS = 3
// Four of a braille cell's eight dots lit, the four turning round the cell a
// dot at a time (the ring is dots 1 4 5 6 8 7 3 2, clockwise from top left).
const SPIN = '⠹⢸⣰⣤⣆⡇⠏⠛'
export const BAR_W = 28 // cells in the bar: room for "⢸ 59m 59s / ~59m 59s" and "interrupted after 1h 2m"

const GREEN = '#3fb950'
const AMBER = '#e6b450'
const RED = '#f85149'
const GREY = '#8a8a8a'
// The band's own colour, periwinkle: the model's name, a running row's
// spinner, a finished review's ✓, and (as ON_BLUE and ON_DONE) the bar's ground.
// Not one of the colours that say how a run went (green, amber, red).
const BLUE = '#89b4fa'
const INK = '#ffffff'
type Rgb = readonly [number, number, number]
const ON_BLUE: Rgb = [87, 106, 138] // a running bar: BLUE itself, washed thin over the empty ground
const ON_DONE: Rgb = [44, 82, 148] // a finished review's bar: the same blue, deep
const ON_AMBER: Rgb = [140, 98, 20]
const ON_RED: Rgb = [150, 44, 40]
const ON_EMPTY: Rgb = [46, 46, 46]

const hex = (c: Rgb) => '#' + c.map(x => Math.round(x).toString(16).padStart(2, '0')).join('')
const mix = (a: Rgb, b: Rgb, t: number): Rgb => [0, 1, 2].map(i => a[i]! + (b[i]! - a[i]!) * t) as unknown as Rgb

const DONE = /done · \S+ turns · (\d+)s$/
const STARTED = /^\[[^\]]*\] started (\S+) /
const CALL = /^\[[^\]]*\] turn (\d+) · (\S+) ?(.*)$/
const BACK = /^\[[^\]]*\] turn \d+ ↳ Execute \w+ in \d+s(, \d+ still running)?$/
const READS = new Set(['Read', 'Grep', 'Glob', 'LS'])
const WEB = new Set(['WebSearch', 'FetchUrl'])
// Commands that only look. Anything else droid executes is taken for a check.
const LOOKS = new Set(
  'git cat ls grep rg sed head tail find wc diff awk nl tree stat file which command echo printf pwd jq'.split(' '),
)

/** A length of time, as the row writes it: "45s", "2m 3s", "4m", "1h 2m", "2h". */
export function short(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  if (s < 60) return `${s}s`
  const [big, small] =
    s >= 3600
      ? [`${Math.floor(s / 3600)}h`, `${Math.floor(s / 60) % 60}m`]
      : [`${Math.floor(s / 60)}m`, `${s % 60}s`]
  return small.startsWith('0') ? big : `${big} ${small}`
}

/** How long since a run ended: "just now", "3m ago", "2h ago". */
export function ago(seconds: number): string {
  const m = Math.floor(seconds / 60)
  return m < 1 ? 'just now' : m < 60 ? `${m}m ago` : `${Math.floor(m / 60)}h ago`
}

function since(iso: unknown, now: number): number | null {
  const at = typeof iso === 'string' ? Date.parse(iso) : NaN
  return Number.isNaN(at) ? null : now - at / 1000
}

const isRecheck = (m: Meta) => (m.round ?? 1) > 1
const timedAs = (m: Meta) => `${m.kind || 'review'}|${m.model}|${isRecheck(m)}`

/** Finished durations by kind, model and whether a re-check: what a running bar is measured against. */
export function history(runs: readonly Run[], orphans: readonly LogEnds[]): History {
  const out: History = new Map()
  const add = (key: string, s: number) => out.set(key, [...(out.get(key) ?? []), s])
  for (const { meta } of runs) {
    if (meta.status === 'ok' && meta.model && typeof meta.duration_s === 'number') add(timedAs(meta), meta.duration_s)
  }
  for (const { first, last } of orphans) {
    const s = STARTED.exec(first)
    const d = DONE.exec(last)
    if (s && d) add(`review|${s[1]}|false`, Number(d[1]))
  }
  return out
}

function median(values: readonly number[]): number | null {
  if (values.length === 0) return null
  const sorted = [...values].sort((a, b) => a - b)
  const mid = sorted.length >> 1
  return sorted.length % 2 ? sorted[mid]! : (sorted[mid - 1]! + sorted[mid]!) / 2
}

/**
 * One bar with its text inside, " ⢸ 25s / ~40s      ", the first fraction of
 * its cells on the ground colour. The cell at the edge of the fill shades in
 * as it is covered (a little ahead, to be seen), so the bar moves at every
 * tick and not only when a whole cell fills (on a four-minute estimate, once
 * in eleven seconds). A null fraction is a run with nothing to measure
 * against: a block drifts across instead.
 */
function bar(text: string, ground: Rgb, fraction: number | null, now: number): DroidReviewsSeg[] {
  const cells = (' ' + text).padEnd(BAR_W).slice(0, BAR_W)
  let parts: [Rgb, string][]
  if (fraction === null) {
    const at = Math.floor(now) % (BAR_W - 3)
    parts = [
      [ON_EMPTY, cells.slice(0, at)],
      [ground, cells.slice(at, at + 4)],
      [ON_EMPTY, cells.slice(at + 4)],
    ]
  } else {
    const full = Math.max(0, Math.min(BAR_W, BAR_W * fraction))
    const n = Math.floor(full)
    // ** 0.6: a straight mix keeps the first half of a cell too close to empty to see.
    parts = [
      [ground, cells.slice(0, n)],
      [mix(ON_EMPTY, ground, (full - n) ** 0.6), cells.slice(n, n + 1)],
      [ON_EMPTY, cells.slice(n + 1)],
    ]
  }
  return parts.filter(([, c]) => c).map(([g, c]) => ({ text: c, color: INK, bg: hex(g), bold: true }))
}

const RUNNING_FULL = Math.round(0.8 * BAR_W) / BAR_W // four fifths, on a whole cell: the stop is a clean edge

/** A command without the "cd somewhere &&" it opens with: what it runs. */
const uncd = (command: string) => command.replace(/^(?:\(?\s*cd\s+\S+\s*(?:&&|;)\s*)+/, '')

function activity(tool: string, target: string): string | null {
  if (READS.has(tool)) return 'reading'
  if (WEB.has(tool)) return 'researching'
  if (tool === 'TodoWrite') return 'planning'
  if (tool === 'Skill' || tool === 'ToolSearch') return null // setting up, not the work
  if (tool === 'Execute') {
    const first = uncd(target).replace(/^(?:[A-Za-z_]\w*=\S*\s+)+/, '').trim().split(/\s+/)[0] ?? ''
    const word = first.slice(first.lastIndexOf('/') + 1).replace(/[);]+$/, '')
    return LOOKS.has(word) ? 'reading' : 'running'
  }
  return 'working'
}

/** What droid is doing, in a word or two, from the kinds of call in its last turns. */
export function phase(lines: readonly string[], quiet: number, kind: string): string {
  const calls: [number, string][] = []
  let going: string | null = null // the kind of command still out, if one is
  for (const line of lines) {
    const back = BACK.exec(line)
    if (back) {
      if (!back[1]) going = null
      continue
    }
    const hit = CALL.exec(line)
    if (!hit) continue
    const a = activity(hit[2]!, hit[3]!)
    if (a) calls.push([Number(hit[1]), a])
    if (hit[2] === 'Execute') going = a
  }
  const latest = calls.at(-1)
  if (!latest) return 'starting'
  let top: string
  if (quiet >= QUIET_S) {
    top = going ?? 'thinking'
  } else {
    // The commonest kind in the last turns; the latest wins a tie.
    const recent = calls.filter(([turn]) => turn > latest[0] - RECENT_TURNS).map(([, a]) => a)
    const rank = (a: string) => recent.filter(x => x === a).length * recent.length + recent.lastIndexOf(a)
    top = recent.reduce((best, a) => (rank(a) > rank(best) ? a : best))
  }
  if (top === 'reading') return 'reading files'
  if (top === 'running') return kind === 'review' ? 'running checks' : 'running commands'
  return top
}

/** What has come of a finished review, and how long since its note (null: none yet). */
function triage(m: Meta, endedAgo: number | null, now: number): [DroidReviewsSeg[], number | null] {
  const notes = (Array.isArray(m.responses) ? m.responses : []).filter(
    (n): n is { text: unknown; at?: unknown } => typeof n === 'object' && n !== null && Boolean((n as { text?: unknown }).text),
  )
  const note = notes.at(-1)
  if (!note) {
    // A run with no known end has an infinite age: it must not take the other rows down.
    const waited = endedAgo !== null && Number.isFinite(endedAgo) ? Math.floor(endedAgo / 60) : 0
    return [[{ text: 'awaiting triage' + (waited ? ` for ${short(waited * 60)}` : '') + '...' }], null]
  }
  const noted = since(note.at, now)
  const text = String(note.text).split(/\s+/).filter(Boolean).join(' ')
  return [
    [
      { text: 'triaged', color: GREEN },
      { text: `${noted !== null ? ' ' + ago(noted) : ''}: ${text}`, color: GREY },
    ],
    noted,
  ]
}

function who(m: Meta): { label: string; model: string; aside: string; width: number } {
  const label = m.kind === 'feedback' ? 'droid-feedback' : 'droid-review'
  const model = m.model_name || m.model || '?'
  const aside = (m.effort ? ` ${m.effort}` : '') + (isRecheck(m) ? ` (round ${m.round})` : '')
  return { label, model, aside, width: `${label} · ${model}${aside}`.length }
}

/** The rows to show now (seconds since the epoch), oldest run first; none when nothing is running or recent. */
export function rows(runs: readonly Run[], hist: History, now: number): DroidReviewsRow[] {
  const seen = runs.map(run => {
    const { meta, logAt } = run
    const silent = logAt === null ? 0 : now - logAt
    const status = meta.status === 'running' && (!run.isAlive || silent > STALE_S) ? 'stopped' : meta.status
    // A "stopped" run has no finish recorded, so its log's last write stands in.
    const ended = status === 'running' ? null : (since(meta.finished, now) ?? (logAt === null ? Infinity : silent))
    const [triaged, noted] = triage(meta, ended, now)
    return { run, status, silent, ended, triaged, noted }
  })
  // A finished row stays a quarter of an hour after it ended, or after it was
  // triaged if that came later; a review still waiting to be triaged, an hour.
  const shown = seen.filter(({ status, ended, noted }) => {
    if (ended === null) return true
    const last = noted !== null ? Math.min(ended, noted) : ended
    return last <= SHOW_FINISHED_S || (status === 'ok' && noted === null && ended <= SHOW_UNTRIAGED_S)
  })
  // By start, then by name: a fan-out starts its models in the same second, and
  // they must keep their places from one tick to the next.
  const order = ({ run }: (typeof shown)[number]) => `${run.meta.started ?? ''} ${run.name}`
  shown.sort((a, b) => (order(a) < order(b) ? -1 : order(a) > order(b) ? 1 : 0))
  const width = Math.max(0, ...shown.map(s => who(s.run.meta).width))

  return shown.map(({ run, status, silent, ended, triaged }) => {
    const m = run.meta
    const w = who(m)
    // "droid-review · Gemini 3.8 Flash max (round 2)": the command that ran,
    // droid's name for the model (else its id) with the effort when one was
    // named, and which round on the same review it is if not the first. Padded
    // to the widest so the bars line up.
    const name: DroidReviewsSeg[] = [
      { text: w.label },
      { text: ' · ', color: GREY },
      { text: w.model, color: BLUE },
      { text: w.aside + ' '.repeat(width - w.width), color: GREY },
    ]
    const row = (lead: DroidReviewsSeg, meter: DroidReviewsSeg[], tail: DroidReviewsSeg[]): DroidReviewsRow => ({
      key: run.name,
      segs: [lead, { text: ' ' }, ...name, { text: '  ' }, ...meter, { text: '  ' }, ...tail].filter(s => s.text),
    })

    if (status === 'running') {
      const elapsed = since(m.started, now) ?? 0
      // The spinner leads the row and the bar: its time then starts in the
      // column a finished bar's does after its ✓.
      const spin = SPIN[Math.floor(now) % SPIN.length]!
      const estimate = median(hist.get(timedAs(m)) ?? [])
      const last = [...run.lines].reverse().map(l => CALL.exec(l)).find(Boolean)
      let doing = last ? `turn ${last[1]} · ${`${last[2]} ${uncd(last[3]!)}`.trim()}` : ''
      const nowDoing = phase(run.lines, silent, m.kind || 'review')
      const isHeld = silent >= QUIET_S && nowDoing !== 'starting' // thinking for, running checks for
      if (isHeld) doing = `for ${short(silent)}${doing ? ' · ' + doing : ''}`
      const meter = estimate
        ? bar(`${spin} ${short(elapsed)} / ~${short(estimate)}`, ON_BLUE, RUNNING_FULL * Math.min(1, elapsed / estimate), now)
        : bar(`${spin} ${short(elapsed)}`, ON_BLUE, null, now)
      return row({ text: spin, color: BLUE }, meter, [
        { text: nowDoing },
        { text: doing ? (isHeld ? ' ' : ' · ') + doing : '', color: GREY },
      ])
    }

    const took = typeof m.duration_s === 'number' ? short(m.duration_s) : '?'
    const when = ago(ended ?? 0)
    if (status === 'ok') {
      return row({ text: '✓', color: BLUE, bold: true }, bar(`✓ ${took} · ${m.turns ?? '?'} turns`, ON_DONE, 1, now), triaged)
    }
    if (status === 'failed') {
      const err = String(m.error ?? '').split(/\s+/).filter(Boolean).join(' ')
      return row({ text: '✗', color: RED, bold: true }, bar(`failed after ${took}`, ON_RED, 1, now), [
        { text: when + (err ? ` · ${err}` : ''), color: GREY },
      ])
    }
    if (status === 'interrupted') {
      return row({ text: '✗', color: AMBER, bold: true }, bar(`interrupted after ${took}`, ON_AMBER, 1, now), [
        { text: when, color: GREY },
      ])
    }
    return row({ text: '✗', color: AMBER, bold: true }, bar('stopped', ON_AMBER, 1, now), [
      { text: `${when} · its process is gone`, color: GREY },
    ])
  })
}
