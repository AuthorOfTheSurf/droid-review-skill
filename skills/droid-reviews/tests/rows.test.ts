// What a row says for each state a run's metadata can be in: rows.ts on its
// own, handed runs as register.tsx would have read them. No files, no clock.

import { expect, test } from 'claude-code/testing'

import type { DroidReviewsRow, DroidReviewsSeg } from '../types'
import { BAR_W, QUIET_S, STALE_S, ago, history, phase, rows, short } from '../hooks/rows'
import type { LogEnds, Meta, Run } from '../hooks/rows'

const NOW = Date.parse('2026-10-05T19:00:00+08:00') / 1000
const iso = (secondsAgo: number) => new Date((NOW - secondsAgo) * 1000).toISOString()

// The bar's grounds, as rows.ts mixes them.
const ON_BLUE = '#576a8a'
const ON_DONE = '#2c5294'
const ON_RED = '#962c28'
const ON_EMPTY = '#2e2e2e'
const GREEN = '#3fb950'
const GREY = '#8a8a8a'
const BLUE = '#89b4fa'
const STOP = Math.round(BAR_W * 0.8) // where a running bar stops

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

/** The cells of a row's bar: the ones on a ground. */
const cells = (row: DroidReviewsRow) => row.segs.filter(seg => seg.bg)
/** How many of a bar's cells sit on a ground colour. */
const filled = (row: DroidReviewsRow, ground: string) =>
  cells(row).filter(seg => seg.bg === ground).reduce((n, seg) => n + seg.text.length, 0)
const seg = (row: DroidReviewsRow, said: string): DroidReviewsSeg | undefined => row.segs.find(s => s.text === said)

const READ = ['[0m20s] turn 2 · Read x']

test('nothing running or recent: no rows', () => {
  expect(show([run('old', { status: 'ok', finished: iso(3601), duration_s: 40, turns: 9 })])).toEqual([])
})

test('a running row shows the model, the effort, the time so far and the last call', () => {
  const row = only(show([run('a', { log: ['[0m01s] started glm-5.3-flash (reasoning high) session s', '[0m20s] turn 3 · Execute git diff --stat'] })]))
  expect(row).toContain('droid-review · glm-5.3-flash high')
  expect(row).toMatch(/ {3}\S 25s {3,}reading files/) // the spinner, then the time
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

test('the bar is one piece with its text inside, never wider', () => {
  const row = only(draw([run('ok', { status: 'ok', finished: iso(60), duration_s: 92, turns: 14 })]))
  expect(text(row)).toContain('   ✓ 1m 32s · 14 turns' + ' '.repeat(BAR_W - 20) + '  awaiting')
  expect(filled(row, ON_DONE)).toBe(BAR_W) // done: full
  // A model with an hour-long median: the longest text a bar holds still fits its cells.
  const long = only(draw([finished('past', { duration_s: 3599 }), run('a', { started: iso(3599), log: READ })]))
  expect(cells(long).reduce((n, s) => n + s.text.length, 0)).toBe(BAR_W)
})

test('the bar fills with time, up to the stop', () => {
  const [late, early] = draw([
    finished('ok0', { duration_s: 40 }),
    finished('ok1', { duration_s: 40 }),
    run('a', { started: iso(20), log: READ }),
    run('b', { started: iso(90), log: READ }),
  ])
  expect(filled(early!, ON_BLUE)).toBe(STOP / 2) // half the estimate
  expect(filled(late!, ON_BLUE)).toBe(STOP) // past it: the stop
  expect(text(late!)).toMatch(/ {3}\S 1m 30s \/ ~40s /)
})

test('a running bar stops at four fifths however late', () => {
  const row = only(draw([finished('ok', { duration_s: 40 }), run('a', { started: iso(40000), log: READ })]))
  expect(filled(row, ON_BLUE)).toBe(STOP) // a thousand times over: still blue, still open
  expect(filled(row, ON_EMPTY)).toBe(BAR_W - STOP)
})

test('the cell at the edge of the fill shades in between whole cells', () => {
  // On a 220s estimate the stop's 22 cells fill one in ten seconds: 10.2, 10.5 and 10.8 cells.
  const edges = [102, 105, 108].map(elapsed => {
    const row = only(draw([finished('ok', { duration_s: 220 }), run('a', { started: iso(elapsed), log: READ })]))
    expect(filled(row, ON_BLUE)).toBe(10)
    return cells(row)[1]!.bg
  })
  expect(new Set(edges).size).toBe(3)
  expect(edges).not.toContain(ON_EMPTY)
  expect(edges).not.toContain(ON_BLUE)
})

test('with no history a block drifts across the bar', () => {
  const at = (now: number) => {
    const row = only(draw([run('a', { log: READ })], [], now))
    expect(filled(row, ON_BLUE)).toBe(4)
    return cells(row).findIndex(s => s.bg === ON_BLUE) === 0 ? 0 : cells(row)[0]!.text.length
  }
  expect(at(NOW)).not.toBe(at(NOW + 1))
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

test('the spinner turns a frame each second', () => {
  const frames = [0, 1, 2, 3].map(i => only(show([run('a', { log: READ })], [], NOW + i))[0])
  expect(new Set(frames).size).toBe(4)
})

test('times in the bar are short, and a running bar leads with the spinner', () => {
  expect([0, 45, 60, 123, 240, 3599, 3600, 3725, 7200].map(short)).toEqual(['0s', '45s', '1m', '2m 3s', '4m', '59m 59s', '1h', '1h 2m', '2h'])
  const [done, running] = show([
    run('ok', { status: 'ok', finished: iso(60), duration_s: 134, turns: 21, started: iso(300) }),
    run('a', { started: iso(123), log: READ }),
  ])
  expect(running![0]).toBe(running![running!.indexOf('2m 3s') - 2]) // the row's spinner, again in its bar
  expect(done).toContain('   ✓ 2m 14s · 21 turns')
  // So the two times start in the same column.
  expect(done!.indexOf('2m 14s')).toBe(running!.indexOf('2m 3s'))
})

test('a quiet row says for how long', () => {
  const log = ['[0m10s] turn 2 · Read a', '[0m20s] turn 3 · Execute cd /repo && npm test']
  expect(only(show([run('a', { log, quiet: 45 })]))).toContain('   running checks for 45s · turn 3 · Execute npm test') // and no cd
  const back = [...log, '[1m00s] turn 3 ↳ Execute returned in 40s']
  expect(only(show([run('a', { log: back, quiet: 45 })]))).toContain('   thinking for 45s · turn 3 · Execute npm test') // the call, not its return
})

test('a dead process reads as stopped, and goes once its log is old', () => {
  expect(only(show([run('a', { isAlive: false, log: READ })]))).toMatch(/ {3}stopped {3,}just now · its process is gone/)
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
  expect(all).toMatch(/ {3}✓ 1m 32s · 14 turns {3,}awaiting triage for 14m\.\.\.$/m)
  expect(all).toMatch(/ {3}failed after 3s {3,}just now · droid reported: no auth/)
  expect(all).toMatch(/ {3}interrupted after 7s {3,}just now/)
  expect([0, 59, 60, 899, 3600, 7300].map(ago)).toEqual(['just now', 'just now', '1m ago', '14m ago', '1h ago', '2h ago'])
  // The result fills the bar, in its colour.
  const ok = drawn.find(row => text(row).includes('   ✓'))!
  expect(filled(ok, ON_DONE)).toBe(BAR_W)
  expect(ok.segs[0]).toEqual({ text: '✓', color: BLUE, bold: true }) // a review that finished: the model's blue
  expect(filled(drawn.find(row => text(row).includes('failed after'))!, ON_RED)).toBe(BAR_W)
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
