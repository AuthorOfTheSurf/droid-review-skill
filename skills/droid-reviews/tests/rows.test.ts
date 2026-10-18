// What a row says for each state a run's metadata can be in: rows.ts on its
// own, handed runs as register.tsx would have read them. No files, no clock.

import { expect, test } from 'claude-code/testing'

import type { DroidReviewsRow, DroidReviewsSeg } from '../types'
import { BAR_W, DOTS, FINISH_S, QUIET_S, STALE_S, STOP, TEXT_W, ago, history, paint, phase, plan, rows, short } from '../hooks/rows'
import type { LogEnds, Meta, Run } from '../hooks/rows'

const NOW = Date.parse('2026-10-05T19:00:00+08:00') / 1000
const iso = (secondsAgo: number) => new Date((NOW - secondsAgo) * 1000).toISOString()

// The bar's colours, as rows.ts draws them.
const RIBBON = '#6888c4'
const FINISHED = '#89b4fa'
// Each row's own colour, by the hue its run recorded: full (its name, ✓, finished bar) and dim (its running bar).
const HUES = [
  { full: '#89b4fa', dim: '#6888c4' }, // blue
  { full: '#a6e3a1', dim: '#76aa72' }, // green
  { full: '#f38ba8', dim: '#be6880' }, // pastel pink
  { full: '#fab387', dim: '#c48662' }, // orange
  { full: '#cba6f7', dim: '#987ac0' }, // lavender
]
const FAILED = '#f85149'
const TRACK = '#444444'
const GREEN = '#3fb950'
const GREY = '#8a8a8a'
const BLUE = '#89b4fa'

type Given = Meta & { log?: string[]; quiet?: number; isAlive?: boolean }

/** A run as register.tsx hands it over: running on a live process unless told otherwise, its log just written. */
function run(name: string, { log, quiet = 0, isAlive = true, ...meta }: Given = {}): Run {
  return {
    name,
    meta: { kind: 'review', status: 'running', pid: 4242, model: 'glm-5.3-flash', effort: 'high', started: iso(25), finished: null, ...meta },
    logAt: log ? NOW - quiet : null,
    isAlive,
    lines: log ?? [],
  }
}

const finished = (name: string, meta: Meta = {}) => run(name, { status: 'ok', finished: iso(9999), turns: 5, ...meta })

/** A run from before the metadata: only the ends of its log. */
const legacy = (model: string, seconds: number): LogEnds => ({
  first: `[0m01s] started ${model} (reasoning high) session abc`,
  last: `[${Math.floor(seconds / 60)}m${String(seconds % 60).padStart(2, '0')}s] done · 9 turns · ${seconds}s`,
})

const draw = (runs: Run[], orphans: LogEnds[] = [], now = NOW) => rows(runs, history(runs, orphans), now)
const text = (row: DroidReviewsRow) => row.segs.map(seg => seg.text).join('')
const show = (runs: Run[], orphans: LogEnds[] = [], now = NOW) => draw(runs, orphans, now).map(text)
const only = <T>(list: T[]): T => {
  expect(list).toHaveLength(1)
  return list[0]!
}

// A dot's bit in a braille cell, by column (left, right) and height (bottom up).
const BIT = [
  [0x40, 0x04, 0x02, 0x01],
  [0x80, 0x20, 0x10, 0x08],
]
type Col = { h: number; color: string }
/** The bar read back as its columns: each one's height (its dots lit from the bottom) and its cell's colour. */
function columns(row: DroidReviewsRow): Col[] {
  const chars = row.segs.flatMap(seg => [...seg.text].map(ch => ({ ch, color: seg.color ?? '' })))
  const at = chars.findIndex((_, i) => chars.slice(i, i + BAR_W).every(c => c.ch >= '\u2800' && c.ch <= '\u28ff') && chars.length >= i + BAR_W)
  expect(at).toBeGreaterThan(0)
  return chars.slice(at, at + BAR_W).flatMap(({ ch, color }) => {
    const bits = ch.charCodeAt(0) - 0x2800
    return BIT.map(side => ({ h: side.findIndex(b => !(bits & b)) === -1 ? 4 : side.findIndex(b => !(bits & b)), color }))
  })
}
/** How many columns the ribbon (or the blob) covers: the ones taller than the track in its colour. */
const ribbon = (row: DroidReviewsRow, color = RIBBON) => columns(row).filter(c => c.color === color && c.h >= 2).length
const seg = (row: DroidReviewsRow, said: string): DroidReviewsSeg | undefined => row.segs.find(s => s.text === said)

const READ = ['[0m20s] turn 2 · Read x']

test('nothing running or recent: no rows', () => {
  expect(show([run('old', { status: 'ok', finished: iso(3601), duration_s: 40, turns: 9 })])).toEqual([])
})

test('a running row shows the model, the effort, the time so far and the last call', () => {
  const row = only(show([run('a', { log: ['[0m01s] started glm-5.3-flash (reasoning high) session s', '[0m20s] turn 3 · Execute git diff --stat'] })]))
  expect(row).toContain('droid-review · glm-5.3-flash high')
  expect(row).toMatch(/[⠀-⣿]{20} 25s {3,}reading files/) // the bar, then the time
  expect(row).toContain('turn 3 · Execute git diff --stat')
  expect(row).not.toContain('/ ~') // no history: no estimate
})

test('just started says starting', () => {
  expect(only(show([run('a', { log: ['[0m01s] started glm-5.3-flash (reasoning high) session s'] })]))).toContain('starting')
})

test('the estimate is the median of the same model\'s finished runs', () => {
  const past = [30, 40, 300].map((d, i) => finished(`ok${i}`, { duration_s: d }))
  const row = only(
    show([
      ...past,
      finished('other', { model: 'gemini-3.8-flash', duration_s: 5 }),
      run('failed', { status: 'failed', finished: iso(9999), duration_s: 1 }),
      run('a', { log: READ }),
    ]),
  )
  expect(row).toContain('25s / ~40s')
})

test('the estimate counts logs from before the metadata', () => {
  const orphans = [legacy('glm-5.3-flash', 50), legacy('glm-5.3-flash', 70)]
  expect(only(show([run('a', { log: READ })], orphans))).toContain('/ ~1m ')
})

test('the bar is braille the same width, what it says padded beside it', () => {
  const row = only(draw([run('ok', { status: 'ok', finished: iso(60), duration_s: 92, turns: 14 })]))
  expect(text(row)).toContain(' ' + '⣤'.repeat(BAR_W) + ' ' + '1m 32s · 14 turns'.padEnd(TEXT_W) + '  awaiting')
  expect(ribbon(row, FINISHED)).toBe(DOTS) // done: whole
  // A model with an hour-long median: the longest time still fits its room.
  const long = text(only(draw([finished('past', { duration_s: 3599 }), run('a', { started: iso(3599), log: READ })])))
  expect(long).toMatch(new RegExp(`[⠀-⣿]{${BAR_W}} 59m 59s / ~59m 59s {2,}reading`))
})

test('the ribbon grows with time, up to the stop', () => {
  const [late, early] = draw([
    finished('ok0', { duration_s: 40 }),
    finished('ok1', { duration_s: 40 }),
    run('a', { started: iso(20), log: READ }),
    run('b', { started: iso(90), log: READ }),
  ])
  expect(ribbon(early!)).toBe(STOP / 2) // half the estimate
  expect(ribbon(late!)).toBe(STOP) // past it: the stop
  expect(columns(late!)[STOP]).toEqual({ h: 1, color: TRACK }) // four fifths is not marked: past the ribbon, only the track
  expect(text(late!)).toMatch(new RegExp(`[⠀-⣿]{${BAR_W}} 1m 30s / ~40s `))
})

test('a row takes the colour of its model, five of them round and round, blue for a run that recorded none', () => {
  const hues = [0, 1, 2, 3, 4, 5, 1, null]
  const drawn = draw([finished('past', { duration_s: 40 }), ...hues.map((hue, n) => run(`r${n}`, { started: iso(30 - n), log: READ, hue }))])
  const want = [0, 1, 2, 3, 4, 0, 1, 0].map(n => HUES[n]!)
  expect(drawn.map(row => row.segs.find(seg => seg.text === 'glm-5.3-flash')?.color)).toEqual(want.map(h => h.full))
  expect(drawn.map(row => columns(row)[0]!.color)).toEqual(want.map(h => h.dim))
  const failed = only(draw([run('b', { status: 'failed', finished: iso(5), duration_s: 3, hue: 1 })]))
  expect(columns(failed)[0]!.color).toBe(FAILED) // a failure fills red, not its model's green
})

test('a running bar stops at four fifths however late', () => {
  const cols = columns(only(draw([finished('ok', { duration_s: 40 }), run('a', { started: iso(40000), log: READ })])))
  expect(cols.filter(c => c.color === RIBBON).length).toBe(STOP) // a thousand times over: still blue, still open
  expect(cols.slice(STOP + 2)).toEqual(Array(DOTS - STOP - 2).fill({ h: 1, color: TRACK })) // the open fifth: the track
})

test('the ribbon ends clean against the track', () => {
  // On a 320s estimate the stop's 32 dots fill one in ten seconds.
  for (const elapsed of [105, 115]) {
    const cols = columns(only(draw([finished('ok', { duration_s: 320 }), run('a', { started: iso(elapsed), log: READ })])))
    const n = Math.round(elapsed / 10)
    expect(cols.slice(0, n).every(c => c.h === 2)).toBe(true)
    if (n % 2) expect(cols[n]!.h).toBe(0) // the track's dot in the ribbon's last cell is left out
  }
})

test('with no history a blob drifts along the track', () => {
  const at = (now: number) => columns(only(draw([run('a', { log: READ })], [], now))).findIndex(c => c.h >= 2)
  expect(at(NOW + 1) - at(NOW)).toBe(2)
  expect(columns(only(draw([run('a', { log: READ })]))).filter(c => c.h >= 2)).toHaveLength(6)
})

test('feedback is timed against feedback', () => {
  const runs = [finished('r', { duration_s: 600 }), finished('f', { kind: 'feedback', duration_s: 60 }), run('a', { kind: 'feedback', log: READ })]
  expect(only(show(runs))).toContain('/ ~1m ')
})

const said = (calls: [number, string][], quiet = 0, kind = 'review') =>
  phase(['[0m01s] started glm (reasoning high) session s', ...calls.map(([turn, call], i) => `[0m${String(i).padStart(2, '0')}s] turn ${turn} · ${call}`)], quiet, kind)

test('the phase is the commonest kind of call in the last turns', () => {
  expect(said([])).toBe('starting')
  expect(said([[1, 'Skill review']])).toBe('starting')
  expect(said([[1, 'Read a'], [2, 'Grep x'], [3, 'Glob *.py']])).toBe('reading files')
  expect(said([[1, 'Read a'], [2, 'WebSearch x'], [3, 'FetchUrl http://y']])).toBe('researching')
  expect(said([[1, 'TodoWrite plan']])).toBe('planning')
  expect(said([[1, 'GenerateImage x']])).toBe('working')
  // Twenty reads long ago do not outweigh what it is doing now.
  const reads = Array.from({ length: 20 }, (_, i): [number, string] => [i + 1, 'Read f'])
  expect(said([...reads, [21, 'Execute npm test'], [22, 'Execute npm run lint'], [23, 'Read out.log']])).toBe('running checks')
  expect(said([[1, 'Read a'], [2, 'Execute npm test']])).toBe('running checks') // a tie: the latest
})

test('the phase tells looking from running by the command\'s first word', () => {
  for (const look of ['git diff --stat', 'cd /repo && git log --oneline', 'cat x', 'FOO=1 grep -n x y', '(cd sub && ls)']) {
    expect(said([[1, `Execute ${look}`]])).toBe('reading files')
  }
  for (const check of ['npm test', 'python3 t.py', 'cd /repo && .claude/skills/x/regress.sh', 'bash -n x.sh']) {
    expect(said([[1, `Execute ${check}`]])).toBe('running checks')
  }
  expect(said([[1, 'Execute npm test']], 0, 'feedback')).toBe('running commands')
})

test('gone quiet it is thinking, unless a command is still going', () => {
  expect(said([[1, 'Read a'], [2, 'WebSearch x']], QUIET_S)).toBe('thinking')
  expect(said([[1, 'Read a'], [2, 'WebSearch x']], QUIET_S - 1)).toBe('researching')
  expect(said([[1, 'Read a'], [2, 'Execute npm test']], 300)).toBe('running checks')
})

test('a command that came back is not still running', () => {
  const log = ['[0m10s] turn 1 · Read a', '[0m20s] turn 2 · Execute npm test']
  const back = '[1m15s] turn 2 ↳ Execute returned in 55s'
  expect(phase(log, 300, 'review')).toBe('running checks')
  expect(phase([...log, back], 300, 'review')).toBe('thinking') // quiet since it returned
  expect(phase([...log, back], 5, 'review')).toBe('running checks') // just back: still what it is at
  expect(phase([...log, '[1m15s] turn 2 ↳ Execute failed in 55s'], 300, 'review')).toBe('thinking')
  // Two started together: one back, one still out.
  const two = [...log, '[0m20s] turn 2 · Execute npm run lint', '[0m30s] turn 2 ↳ Execute returned in 10s, 1 still running']
  expect(phase(two, 300, 'review')).toBe('running checks')
  expect(phase([...two, back], 300, 'review')).toBe('thinking')
  // A command that only looks, still out, is not a check.
  expect(phase(['[0m20s] turn 2 · Execute git log -S x'], 300, 'review')).toBe('reading files')
})

test('a running row leads with the phase, in the theme\'s own colour', () => {
  const row = only(draw([run('a', { log: ['[0m10s] turn 2 · Read a', '[0m20s] turn 3 · Execute git diff --stat'] })]))
  expect(text(row)).toContain('   reading files · turn 3 · Execute git diff --stat')
  expect(seg(row, 'reading files')).toEqual({ text: 'reading files' }) // not grey, and not bold
})

test('held still, the spinner turns a frame each second', () => {
  const frames = [0, 1, 2, 3, 4, 5, 6, 7, 8].map(i => only(show([run('a', { log: READ })], [], NOW + i))[0])
  expect(new Set(frames).size).toBe(8) // every frame, one a second
  expect(frames[8]).toBe(frames[0])
})

test('times beside the bar are short, and start in one column', () => {
  expect([0, 45, 60, 123, 240, 3599, 3600, 3725, 7200].map(short)).toEqual(['0s', '45s', '1m', '2m 3s', '4m', '59m 59s', '1h', '1h 2m', '2h'])
  const [done, running] = show([
    run('ok', { status: 'ok', finished: iso(60), duration_s: 134, turns: 21, started: iso(300) }),
    run('a', { started: iso(123), log: READ }),
  ])
  expect(done).toMatch(/^✓ /)
  expect(done).toContain(' 2m 14s · 21 turns')
  expect(done!.indexOf('2m 14s')).toBe(running!.indexOf('2m 3s'))
})

test('a quiet row says for how long', () => {
  const log = ['[0m10s] turn 2 · Read a', '[0m20s] turn 3 · Execute cd /repo && npm test']
  expect(only(show([run('a', { log, quiet: 45 })]))).toContain('   running checks for 45s · turn 3 · Execute npm test') // and no cd
  const back = [...log, '[1m00s] turn 3 ↳ Execute returned in 40s']
  expect(only(show([run('a', { log: back, quiet: 45 })]))).toContain('   thinking for 45s · turn 3 · Execute npm test') // the call, not its return
})

test('a dead process reads as stopped, and goes once its log is old', () => {
  expect(only(show([run('a', { isAlive: false, log: READ })]))).toMatch(/[⠀-⣿] stopped {3,}just now · its process is gone/)
  expect(show([run('a', { isAlive: false, log: READ, quiet: 3600 })])).toEqual([])
})

test('a live pid whose log has been silent an hour reads as stopped', () => {
  // Killed outright, its pid reused: the pid says alive, the log says not.
  expect(show([run('a', { log: READ, quiet: STALE_S + 60 })])).toEqual([]) // stopped, and long enough ago to hide
  expect(only(show([run('a', { log: READ, quiet: STALE_S - 60 })]))).toContain('turn 2') // still within the hour: running
})

test('finished rows show for fifteen minutes', () => {
  const drawn = draw([
    run('ok', { status: 'ok', finished: iso(890), duration_s: 92, turns: 14 }),
    run('bad', { status: 'failed', finished: iso(5), duration_s: 3, error: 'droid reported:  no\nauth' }),
    run('int', { status: 'interrupted', finished: iso(1), duration_s: 7 }),
    run('gone', { status: 'failed', finished: iso(901), duration_s: 1, error: 'x' }),
  ])
  expect(drawn).toHaveLength(3)
  const all = drawn.map(text).join('\n')
  expect(all).toMatch(/^✓ .*[⠀-⣿] 1m 32s · 14 turns {3,}awaiting triage for 14m\.\.\.$/m)
  expect(all).toMatch(/[⠀-⣿] failed after 3s {3,}just now · droid reported: no auth/)
  expect(all).toMatch(/[⠀-⣿] interrupted after 7s {3,}just now/)
  expect([0, 59, 60, 899, 3600, 7300].map(ago)).toEqual(['just now', 'just now', '1m ago', '14m ago', '1h ago', '2h ago'])
  // The result fills the bar, in its colour.
  const ok = drawn.find(row => text(row).startsWith('✓'))!
  expect(ribbon(ok, FINISHED)).toBe(DOTS)
  expect(ok.segs[0]).toEqual({ text: '✓', color: BLUE, bold: true }) // a review that finished: its model's colour, blue with none recorded
  expect(ribbon(drawn.find(row => text(row).includes('failed after'))!, FAILED)).toBe(DOTS)
})

test('re-checks say their round', () => {
  const drawn = draw([
    run('a', { round: 2, log: READ }),
    run('b', { round: 3, kind: 'feedback', model: 'gemini-3.8-flash', log: READ }),
    run('c', { round: 1, model: 'grok-4.7', log: READ }),
  ])
  const all = drawn.map(text).join('\n')
  expect(all).toContain('droid-review · glm-5.3-flash high (round 2)')
  expect(all).toContain('droid-feedback · gemini-3.8-flash high (round 3)')
  expect(all).toMatch(/droid-review · grok-4\.7 high {4,}\S/) // padded to the widest
  // The command in the theme's own colour, the model in its one, what qualifies them grey.
  const recheck = drawn.find(row => text(row).includes('(round 2)'))!
  expect(seg(recheck, 'droid-review')).toEqual({ text: 'droid-review' })
  expect(seg(recheck, 'glm-5.3-flash')?.color).toBe(BLUE)
  expect(recheck.segs.find(s => s.text.startsWith(' high (round 2)'))?.color).toBe(GREY)
})

test('re-checks are timed against re-checks', () => {
  const [first, again] = show(
    [
      finished('first', { duration_s: 300 }),
      finished('again', { round: 2, duration_s: 60 }),
      run('a', { round: 1, started: iso(26), log: READ }),
      run('b', { round: 2, log: READ }),
    ],
    [legacy('glm-5.3-flash', 600)], // no metadata: a first round
  )
  expect(first).toContain('/ ~7m 30s') // first rounds: the median of 300 and 600
  expect(again).toContain('/ ~1m ') // re-checks: 60
})

test('shows droid\'s name for the model, and times by its id', () => {
  const sol = { model_name: 'GPT-6.1 Sol', model: 'gpt-6.1-sol' }
  const all = show([
    finished('ok', { ...sol, effort: null, duration_s: 120 }),
    run('a', { ...sol, log: READ }),
    run('b', { started: iso(30), log: READ }), // an older run: no name recorded
  ]).join('\n')
  expect(all).toContain('· GPT-6.1 Sol high')
  expect(all).toContain('/ ~2m ') // its estimate, found by id
  expect(all).toContain('· glm-5.3-flash high') // the id
})

test('feedback runs are labelled', () => {
  expect(only(show([run('a', { kind: 'feedback', log: READ })]))).toContain('droid-feedback · glm-5.3-flash high')
})

test('rows line up across models', () => {
  const [a, b] = show([
    run('a', { started: iso(30), log: READ }),
    run('b', { started: iso(20), model: 'gemini-3.8-flash', effort: null, log: READ }),
  ])
  expect(b).toMatch(/droid-review · gemini-3\.8-flash {4,}\S/) // no effort named: none shown
  expect(a!.indexOf(' 25s')).toBe(b!.indexOf(' 35s')) // the bar starts in the same column
})

test('rows are ordered by start, then by name', () => {
  const [first, second] = show([
    run('late', { started: iso(5), model: 'z-model', log: READ }),
    run('early', { started: iso(50), model: 'a-model', log: READ }),
  ])
  expect(first).toContain('a-model')
  expect(second).toContain('z-model')
  // A fan-out starts its models in the same second: they keep their places whichever is read first.
  const twins = [run('1-glm', { model: 'glm', log: READ }), run('1-gemini', { model: 'gemini', log: READ })]
  expect(show(twins)).toEqual(show([...twins].reverse()))
})

test('a finished review says what came of it', () => {
  const drawn = draw([
    run('new', { status: 'ok', finished: iso(120), duration_s: 60, turns: 5 }),
    run('done', {
      status: 'ok',
      started: iso(700),
      finished: iso(600),
      duration_s: 60,
      turns: 5,
      responses: [{ at: iso(500), text: 'first' }, { at: iso(180), text: 'fixed 2;  rejected the race' }],
    }),
  ])
  const [done, fresh] = drawn.map(text)
  // Waiting is in the theme's own colour; done is green.
  expect(seg(drawn[1]!, 'awaiting triage for 2m...')).toEqual({ text: 'awaiting triage for 2m...' })
  expect(seg(drawn[0]!, 'triaged')?.color).toBe(GREEN)
  expect(fresh).toContain('   awaiting triage for 2m')
  expect(done).toContain('   triaged 3m ago: fixed 2; rejected the race') // the latest note, on one line
})

test('a review waits an hour to be triaged, then a quarter of one after', () => {
  const ok = { status: 'ok', duration_s: 60, turns: 5 }
  const shown = show([
    run('waiting', { ...ok, finished: iso(3500) }),
    run('forgotten', { ...ok, finished: iso(3700) }),
    run('just', { ...ok, finished: iso(5000), responses: [{ at: iso(800), text: 'x' }] }),
    run('long', { ...ok, finished: iso(1000), responses: [{ at: iso(950), text: 'y' }] }),
    run('failed', { status: 'failed', finished: iso(1000), duration_s: 60 }), // nothing to triage
  ])
  expect(shown).toHaveLength(2)
  expect(shown.join('\n')).toContain('awaiting triage for 58m...')
  expect(shown.join('\n')).toContain('triaged 13m ago: x')
})

test('a run with no known end does not take the other rows down', () => {
  // No finish recorded and no log to date it by: its age is unknown (infinite).
  const row = only(
    show([
      run('gone', { status: 'ok', finished: null, duration_s: 1, turns: 1 }),
      run('dead', { isAlive: false }),
      run('a', { log: READ }),
    ]),
  )
  expect(row).toContain('turn 2 · Read x')
})

// In motion: the band painted every frame (band.tsx), not held still.

/** How bright a colour is: its channels summed. */
const bright = (c: string) => [1, 3, 5].reduce((n, i) => n + parseInt(c.slice(i, i + 2), 16), 0)
/** How far the ribbon reaches: the columns before the first one that is track or gap. */
const reach = (row: DroidReviewsRow) => columns(row).findIndex(c => c.h < 2 || c.color === TRACK)

const moving = (runs: Run[], t: number, ended: { at: number; from: number } | null = null) =>
  paint(only(plan(runs, history(runs, []), NOW)), t, { ended })
const ESTIMATE = [finished('ok0', { duration_s: 40 }), finished('ok1', { duration_s: 40 })]
const HOP_S = 0.38 // bounce(): a hop off the wall and back

test('in motion the ribbon hits the stop, flashes against it, springs back and comes to rest there', () => {
  const at = (afterHit: number) => moving([...ESTIMATE, run('a', { started: iso(40), log: READ })], NOW + afterHit)
  const touch = columns(at(0))
  expect(reach(at(0))).toBeGreaterThanOrEqual(STOP)
  expect(touch[STOP - 1]!.h).toBe(2) // pressed against the stop: it flashes at its own height, no taller
  expect(bright(touch[STOP - 1]!.color)).toBeGreaterThan(bright(RIBBON))
  expect(reach(at(HOP_S / 2))).toBeLessThan(STOP) // the first hop off it
  expect(columns(at(HOP_S / 2))[STOP - 1]!.h).toBeLessThan(2)
  const rest = columns(at(5))
  expect(reach(at(5))).toBe(STOP) // at rest: four fifths, as when still
  expect(rest[STOP - 1]).toEqual({ h: 2, color: RIBBON }) // the flash is over
  expect(rest[STOP]).toEqual({ h: 1, color: TRACK })
})

test('every cell of the bar lights an even number of dots, in every state and every frame', () => {
  const dots = (row: DroidReviewsRow) => {
    const bar = text(row).split(' ').find(word => /^[\u2800-\u28ff]{20}$/.test(word))!
    return [...bar].map(ch => (ch.charCodeAt(0) - 0x2800).toString(2).replace(/0/g, '').length)
  }
  const odd: string[] = []
  const look = (what: string, row: DroidReviewsRow) => dots(row).some(n => n % 2) && odd.push(what)
  for (let t = NOW; t < NOW + 12; t += 1 / 30) {
    look('estimate', moving([...ESTIMATE, run('a', { started: iso(30), log: READ })], t))
    look('blob', moving([run('a', { log: READ })], t))
    look('finish', moving([finished('a', { finished: iso(0) })], NOW + ((t - NOW) % FINISH_S), { at: NOW, from: 20 }))
  }
  expect([...new Set(odd)]).toEqual([])
})

test('in motion a swell runs along the ribbon', () => {
  // Where the swell is in each frame of one sweep: the first column of the ribbon standing taller than it.
  const sweep = Math.ceil(NOW / 2.8) * 2.8
  const swells = Array.from({ length: 14 }, (_, i) =>
    columns(moving([...ESTIMATE, run('a', { started: iso(20), log: READ })], sweep + i * 0.1)).slice(0, STOP / 2 - 2).findIndex(c => c.h > 2),
  ).filter(at => at >= 0)
  expect(swells.length).toBeGreaterThan(6)
  expect(swells).toEqual([...swells].sort((a, b) => a - b)) // left to right
  const still = columns(only(draw([...ESTIMATE, run('a', { started: iso(20), log: READ })])))
  expect(still.slice(0, STOP / 2 - 1).every(c => c.h === 2)).toBe(true) // still: none
})

test('in motion the blob flies wall to wall, long in flight, squashed narrow and flashing against each wall', () => {
  const at = (t: number) => columns(moving([run('a', { log: READ })], t)).filter(c => c.h >= 2)
  const cycle = 2 * (1.3 + 0.24)
  const start = Math.ceil(NOW / cycle) * cycle
  const flying = at(start + 0.65)
  const right = at(start + 1.3 + 0.12)
  expect(flying.length).toBeGreaterThan(6)
  expect(Math.max(...flying.map(c => c.h))).toBe(2)
  expect(right.length).toBeLessThan(6)
  expect(Math.max(...right.map(c => c.h))).toBe(2) // no taller against the wall
  expect(bright(columns(moving([run('a', { log: READ })], start + 1.3 + 0.12)).at(-1)!.color)).toBeGreaterThan(bright(RIBBON)) // against the wall: a flash
})

test('a run seen to end rushes its ribbon full, slams into the end and settles in its colour', () => {
  const done = [run('a', { status: 'ok', finished: iso(0), duration_s: 40, turns: 6 })]
  const at = (s: number) => moving(done, NOW + s, { at: NOW, from: STOP })
  expect(reach(at(0))).toBe(STOP) // from where it was
  expect(reach(at(0.2))).toBeGreaterThan(STOP)
  expect(reach(at(0.2))).toBeLessThan(DOTS)
  expect(columns(at(0.36)).at(-1)!.h).toBe(2) // the slam: no taller against the end
  expect(bright(columns(at(0.36)).at(-1)!.color)).toBeGreaterThan(bright(bright(RIBBON) > bright(FINISHED) ? RIBBON : FINISHED)) // but a flash
  expect(reach(at(0.36 + HOP_S / 2))).toBeLessThan(DOTS) // sprung back off it
  expect(at(FINISH_S)).toEqual(only(draw(done, [], NOW + FINISH_S))) // then just as it is drawn still
})

test('the model says what it costs, where the run recorded it', () => {
  const [priced, unpriced] = show([
    run('a', { log: READ, model_name: 'Muse Spark 1.2', price: 0.5, effort: null, started: iso(30) }),
    run('b', { log: READ, model_name: 'GLM-5.3-Flash', effort: null, started: iso(20) }),
  ])
  expect(priced).toContain('droid-review · Muse Spark 1.2 (0.5x)')
  expect(unpriced).toContain('droid-review · GLM-5.3-Flash ')
  expect(unpriced).not.toContain('x)')
})
