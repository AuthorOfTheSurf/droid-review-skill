// What a row says, worked out from what droid-review.sh writes to
// .droid-reviews/: each run's .json (status, model, round, start, pid) and the
// end of its .log (the turn and the tool calls droid has made). Nothing here
// reads a file or the clock: register.tsx does, and hands the result in.
//
//   ⠹ droid-review · GLM-5.3-Flash (0.06x)        ⣤⣤⣤⣤⣤⣤⣤⣤⣴⣀⣀⣀⣀⣀⣀⣀⡆⣀⣀⣀ 25s / ~40s              reading files · turn 3 · Read src/auth.ts
//   ⠹ droid-review · Gemini 3.8 Flash (round 2)   ⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣴⡆⣀⣀⣀ 4m 12s / ~1m 30s        running checks for 50s · turn 9 · Execute npm test
//   ✓ droid-feedback · GPT-6 Luna max             ⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤⣤ 2m 14s · 21 turns       awaiting triage for 3m...
//
// After the dot comes the model, what it cost (its token-price multiplier when
// the run started), and the effort if one was named; "(round 2)" is a re-check
// (--session), the second round.
//
// The bar is a line of braille dots that a ribbon grows along as time passes,
// measured against the median time of this model's finished runs of the same
// kind (review or feedback, first round or re-check) in the same folder. A
// re-check takes a fraction of a first review, and feedback as long as its
// ask, so each is timed against its own kind. The ribbon reaches four fifths
// at that estimate and stops there, however late the run is: how
// much is left is not known, and the open fifth says so. Only a finished run
// fills the bar, in the result's colour. Without any history a blob travels
// the line instead. Beside the bar, the time so far against the estimate, or
// how the run ended.
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

import type { DroidReviewsEnded, DroidReviewsPlan, DroidReviewsRow, DroidReviewsRunning, DroidReviewsSeg } from '../types'

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
  /** The model's token-price multiplier when the run started, as droid's /model picker showed it. */
  price?: number | null
  /** Which of the band's colours the row takes, as the script recorded it: the model's shortcut's place in its list, so one model is always one colour. */
  hue?: number | null
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
const SPIN_HZ = 9 // frames a second: one more than a turn, so where the band is drawn once a second it steps one frame
// The bar is braille: each cell two dots across and four down, so its 20 cells
// are a picture 40 dots wide that the bar is drawn in, a column at a time.
export const BAR_W = 20
export const DOTS = 2 * BAR_W
export const STOP = Math.round((0.8 * DOTS) / 2) * 2 // four fifths, on a whole cell: the stop is a clean edge
export const TEXT_W = 23 // what the bar says beside it: room for "59m 59s / ~59m 59s" and "interrupted after 1h 2m"

const GREEN = '#3fb950'
const AMBER = '#e6b450'
const RED = '#f85149'
const GREY = '#8a8a8a'
type Rgb = readonly [number, number, number]
/**
 * A row's own colour, by its model (the `hue` its run recorded; a run from
 * before that is blue), so a model looks the same in every run and several
 * share each colour: `full` is its model's name, its spinner, a finished review's ✓ and
 * bar; `dim` its bar while it runs, so the bar brightens as it finishes. A
 * failed or stopped bar still fills red or amber.
 */
type Hue = { full: Rgb; dim: Rgb }
const HUES: readonly Hue[] = [
  { full: [137, 180, 250], dim: [104, 136, 196] }, // periwinkle blue
  { full: [166, 227, 161], dim: [118, 170, 114] }, // green
  { full: [243, 139, 168], dim: [190, 104, 128] }, // pastel pink
  { full: [250, 179, 135], dim: [196, 134, 98] }, // orange
  { full: [203, 166, 247], dim: [152, 122, 192] }, // lavender
]
const hueOf = (p: DroidReviewsPlan) => HUES[p.hue % HUES.length]!
const FAILED: Rgb = [248, 81, 73] // RED
const HALTED: Rgb = [230, 180, 80] // AMBER
const TRACK: Rgb = [68, 68, 68] // the line the bar runs along
const SQUEEZE: Rgb = [236, 242, 255] // where a bar presses against what stops it
const WHITE: Rgb = [255, 255, 255]

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

/** One column of the bar: how many of its four dots are lit, from the bottom, and in what colour. */
type Column = { h: number; ink: Rgb }

const SETTLE_S = 1.6
const SHINE_EVERY_S = 2.8
const SHINE_FOR_S = 1.4
const FLY_S = 1.3
const HIT_S = 0.24
const RUSH_S = 0.35
/** How long a bar takes to finish once its run is seen to end. */
export const FINISH_S = RUSH_S + SETTLE_S

// A dot's bit in its braille cell, by column (left, right) and height (bottom up).
const BIT = [
  [0x40, 0x04, 0x02, 0x01],
  [0x80, 0x20, 0x10, 0x08],
] as const
const empty = (): Column[] => Array.from({ length: DOTS }, () => ({ h: 1, ink: TRACK }))

/**
 * The bar's columns as braille, two to a cell, then what it says beside it.
 * A cell takes the colour of its taller column: one colour to a cell is all a
 * terminal draws. So where the ribbon or the blob shares a cell with
 * the track, the track's dot there is left out, which also sets the shape off
 * from the line. A shape stands 2 or 4 dots tall, never 3: a cell whose
 * columns differ by one dot reads as a stray odd glyph (⣴, ⡆), so heights are
 * rounded to even here, the one place every shape passes. The track's single
 * dot stays as it is. Cells of one colour run together into one segment.
 */
function draw(cols: readonly Column[], text: string): DroidReviewsSeg[] {
  const out: DroidReviewsSeg[] = []
  const apart = (a: Column, b: Column) => (a.ink === TRACK && b.ink !== TRACK ? { ...a, h: 0 } : a)
  const even = (col: Column) => (col.h <= 1 ? col : { ...col, h: 2 * Math.round(col.h / 2) })
  for (let c = 0; c < BAR_W; c++) {
    const [l, r] = [even(apart(cols[2 * c]!, cols[2 * c + 1]!)), even(apart(cols[2 * c + 1]!, cols[2 * c]!))]
    let bits = 0
    for (const [side, col] of [l, r].entries()) for (let y = 0; y < Math.min(4, col.h); y++) bits |= BIT[side]![y]!
    const color = hex((r.h > l.h ? r : l).ink)
    const glyph = String.fromCharCode(0x2800 + bits)
    const last = out.at(-1)
    if (last?.color === color) last.text += glyph
    else out.push({ text: glyph, color })
  }
  out.push({ text: ' ' + text.padEnd(TEXT_W) })
  return out
}

/** Lays a ribbon two dots high over the columns before `edge`. */
function ribbon(cols: Column[], edge: number, ink: (x: number) => Rgb): void {
  const end = Math.max(0, Math.min(DOTS, Math.round(edge)))
  for (let x = 0; x < end; x++) cols[x] = { h: 2, ink: ink(x) }
}

/**
 * A bar meeting a wall: how far it has sprung back off it, in dots, and how
 * hard it is pressed against it (1 at each touch), `s` seconds after the first
 * touch. Each hop is lower than the one before; by SETTLE_S it is at rest.
 */
function bounce(s: number, height: number): { off: number; squeeze: number } {
  if (s >= SETTLE_S) return { off: 0, squeeze: 0 }
  const decay = Math.exp(-s / 0.45)
  const hop = Math.abs(Math.sin((Math.PI * s) / 0.38))
  return { off: height * decay * hop, squeeze: decay * (1 - hop) ** 3 }
}

/** The columns just short of `edge` pressed against what stops it: they flash white, at the ribbon's own height (a full-height block there reads as a smudge, not a squeeze). */
function press(cols: Column[], edge: number, squeeze: number): void {
  if (squeeze <= 0.05) return
  for (let d = 0; d < 3; d++) {
    const x = Math.round(edge) - 1 - d
    const col = cols[x]
    if (!col || col.ink === TRACK) continue
    const k = squeeze * (1 - d / 3)
    cols[x] = { ...col, ink: mix(col.ink, SQUEEZE, 0.8 * k) }
  }
}

/** How far a running bar has filled at `t`, in dots: up to the stop at the estimate. */
function reach(m: DroidReviewsRunning, t: number): number {
  return m.estimate ? STOP * Math.max(0, Math.min(1, (t - m.started) / m.estimate)) : 0
}

/**
 * Where the blob of a bar with no estimate is at `t`, in dots: it crosses in
 * FLY_S, stretched long and flat mid-flight, then meets the wall for HIT_S,
 * squashed narrow against it and flashing, and goes back.
 */
function flight(t: number): { from: number; width: number; squeeze: number } {
  const W = 6
  const u = t % (2 * (FLY_S + HIT_S))
  const leg = u < FLY_S + HIT_S ? u : u - FLY_S - HIT_S
  const isLeft = u >= FLY_S + HIT_S // flying left, then at the left wall
  if (leg < FLY_S) {
    const q = leg / FLY_S
    const width = W + 5 * Math.sin(Math.PI * q)
    return { from: (DOTS - width) * (isLeft ? 1 - q : q), width, squeeze: 0 }
  }
  const squeeze = Math.sin((Math.PI * (leg - FLY_S)) / HIT_S)
  const width = W * (1 - 0.6 * squeeze)
  return { from: isLeft ? 0 : DOTS - width, width, squeeze }
}

/**
 * A running bar at `t`. Still (where the band is drawn once a second), a
 * ribbon grows along the track toward the stop at four fifths, or with nothing to
 * measure against, a blob drifts along it. In motion, a swell runs along the
 * ribbon; the ribbon hits the stop at the estimate, flashes against it and
 * springs back a few times before it rests; and the blob flies from wall to
 * wall, long in flight and squashed narrow against each wall.
 */
function running(m: DroidReviewsRunning, t: number, isMoving: boolean, { dim: RIBBON, full }: Hue): DroidReviewsSeg[] {
  const SHINE = mix(full, WHITE, 0.5) // the swell that runs along a running bar
  const elapsed = Math.max(0, t - m.started)
  const text = short(elapsed) + (m.estimate ? ` / ~${short(m.estimate)}` : '')
  const cols = empty()
  if (!m.estimate) {
    const { from, width, squeeze } = isMoving ? flight(t) : { from: (2 * Math.floor(t)) % (DOTS - 5), width: 6, squeeze: 0 }
    for (let x = Math.round(from); x < Math.round(from + width) && x < DOTS; x++) {
      cols[x] = { h: 2, ink: mix(RIBBON, SQUEEZE, 0.8 * squeeze) }
    }
    return draw(cols, text)
  }
  if (!isMoving) {
    ribbon(cols, reach(m, t), () => RIBBON)
    return draw(cols, text)
  }
  const { off, squeeze } = elapsed >= m.estimate ? bounce(elapsed - m.estimate, 3) : { off: 0, squeeze: 0 }
  const edge = reach(m, t) - off
  const swell = -3 + ((t % SHINE_EVERY_S) / SHINE_FOR_S) * (edge + 6)
  ribbon(cols, edge, x => mix(RIBBON, SHINE, Math.max(0, 1 - Math.abs(x + 0.5 - swell) / 3) ** 2))
  for (let x = 0; x < Math.round(edge) - 1; x++) if (Math.abs(x + 0.5 - swell) < 1.5) cols[x] = { ...cols[x]!, h: 4 }
  press(cols, edge, squeeze)
  return draw(cols, text)
}

/**
 * How a run that was seen to end finishes its bar, `s` seconds after: the
 * ribbon rushes on from where it was, quickening, slams into the far end,
 * flashes against it and springs back while it takes the result's colour.
 */
function finishing(text: string, ground: Rgb, from: number, s: number, { dim: RIBBON }: Hue): DroidReviewsSeg[] {
  const cols = empty()
  if (s < RUSH_S) {
    ribbon(cols, from + (DOTS - from) * (s / RUSH_S) ** 2, () => RIBBON)
    return draw(cols, text)
  }
  const after = s - RUSH_S
  const { off, squeeze } = bounce(after, 4)
  const ink = mix(mix(RIBBON, ground, Math.min(1, after / 0.5)), SQUEEZE, 0.4 * Math.exp(-after / 0.3))
  ribbon(cols, DOTS - off, () => ink)
  press(cols, DOTS - off, squeeze)
  return draw(cols, text)
}

/** A finished run's bar: the ribbon whole, in the result's colour. */
function ended(text: string, ground: Rgb): DroidReviewsSeg[] {
  return draw(Array.from({ length: DOTS }, () => ({ h: 2, ink: ground })), text)
}

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
  const price = typeof m.price === 'number' ? ` (${+m.price.toFixed(4)}x)` : ''
  const aside = price + (m.effort ? ` ${m.effort}` : '') + (isRecheck(m) ? ` (round ${m.round})` : '')
  return { label, model, aside, width: `${label} · ${model}${aside}`.length }
}

/**
 * The rows to show now (seconds since the epoch), oldest run first; none when
 * nothing is running or recent. Each is what the row says, but for its bar
 * and spinner, which paint() works out for any moment.
 */
export function plan(runs: readonly Run[], hist: History, now: number): DroidReviewsPlan[] {
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

  return shown.map(({ run, status, silent, ended, triaged }): DroidReviewsPlan => {
    const m = run.meta
    const hue = typeof m.hue === 'number' && m.hue >= 0 ? Math.floor(m.hue) % HUES.length : 0
    const own = hex(HUES[hue]!.full)
    const w = who(m)
    // "droid-review · Gemini 3.8 Flash max (round 2)": the command that ran,
    // droid's name for the model (else its id) with the effort when one was
    // named, and which round on the same review it is if not the first. Padded
    // to the widest so the bars line up.
    const name: DroidReviewsSeg[] = [
      { text: w.label },
      { text: ' · ', color: GREY },
      { text: w.model, color: own },
      { text: w.aside + ' '.repeat(width - w.width), color: GREY },
    ]
    const ending = (lead: DroidReviewsSeg, ground: DroidReviewsEnded['ground'], text: string, tail: DroidReviewsSeg[]) =>
      ({ key: run.name, hue, lead, name, meter: { kind: 'ended', ground, text }, tail }) as const

    if (status === 'running') {
      const elapsed = since(m.started, now) ?? 0
      const last = [...run.lines].reverse().map(l => CALL.exec(l)).find(Boolean)
      let doing = last ? `turn ${last[1]} · ${`${last[2]} ${uncd(last[3]!)}`.trim()}` : ''
      const nowDoing = phase(run.lines, silent, m.kind || 'review')
      const isHeld = silent >= QUIET_S && nowDoing !== 'starting' // thinking for, running checks for
      if (isHeld) doing = `for ${short(silent)}${doing ? ' · ' + doing : ''}`
      return {
        key: run.name,
        hue,
        lead: null,
        name,
        meter: { kind: 'running', started: now - elapsed, estimate: median(hist.get(timedAs(m)) ?? []) },
        tail: [{ text: nowDoing }, { text: doing ? (isHeld ? ' ' : ' · ') + doing : '', color: GREY }],
      }
    }

    const took = typeof m.duration_s === 'number' ? short(m.duration_s) : '?'
    const when = ago(ended ?? 0)
    if (status === 'ok') {
      return ending({ text: '✓', color: own, bold: true }, 'done', `${took} · ${m.turns ?? '?'} turns`, triaged)
    }
    if (status === 'failed') {
      const err = String(m.error ?? '').split(/\s+/).filter(Boolean).join(' ')
      return ending({ text: '✗', color: RED, bold: true }, 'red', `failed after ${took}`, [
        { text: when + (err ? ` · ${err}` : ''), color: GREY },
      ])
    }
    if (status === 'interrupted') {
      return ending({ text: '✗', color: AMBER, bold: true }, 'amber', `interrupted after ${took}`, [{ text: when, color: GREY }])
    }
    return ending({ text: '✗', color: AMBER, bold: true }, 'amber', 'stopped', [
      { text: `${when} · its process is gone`, color: GREY },
    ])
  })
}

const ground = (m: DroidReviewsEnded, hue: Hue): Rgb => ({ done: hue.full, red: FAILED, amber: HALTED })[m.ground]

/** The spinner's frame at `t`. */
const spinAt = (t: number) => SPIN[Math.floor(t * SPIN_HZ) % SPIN.length]!

/**
 * A row as it looks at `t`. `motion` is null where the band is drawn once a
 * second and the bar holds still; where it is drawn every frame, it says
 * when the row was seen to stop running, if it was, and how far its bar had
 * filled then, so the bar can finish from there.
 */
export function paint(p: DroidReviewsPlan, t: number, motion: Motion | null): DroidReviewsRow {
  const m = p.meter
  let meter: DroidReviewsSeg[]
  const hue = hueOf(p)
  if (m.kind === 'running') meter = running(m, t, motion !== null, hue)
  else if (motion?.ended && t - motion.ended.at < FINISH_S) meter = finishing(m.text, ground(m, hue), motion.ended.from, t - motion.ended.at, hue)
  else meter = ended(m.text, ground(m, hue))
  const lead = p.lead ?? { text: spinAt(t), color: hex(hue.full) }
  return { key: p.key, segs: [lead, { text: ' ' }, ...p.name, { text: '  ' }, ...meter, { text: '  ' }, ...p.tail].filter(s => s.text) }
}

export type Motion = { ended: { at: number; from: number } | null }

/** Where a running bar's fill ends at `t`, in dots, as drawn in motion: where it finishes from once its run ends. */
export function filledAt(m: DroidReviewsRunning, t: number): number {
  if (m.estimate) return reach(m, t)
  const { from, width } = flight(t)
  return from + width
}

/** The rows as they look at `now`, held still. */
export const rows = (runs: readonly Run[], hist: History, now: number): DroidReviewsRow[] =>
  plan(runs, hist, now).map(p => paint(p, now, null))
