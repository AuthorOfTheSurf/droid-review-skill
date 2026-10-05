import { expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const FOLDER = '/repo/.droid-reviews'
const at = (clock: string) => Date.parse(`2026-10-05T${clock}+08:00`)
const SURFACES = ['terminal', 'desktop'] as const
const BAND = {
  plugin: 'droid-reviews',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isWorking: false,
    maxRows: 10,
    bodyColumns: 160,
    scroll: { offset: 0, bodyRows: 10 },
    view: {},
  },
} as const

type File = { text: string; mtimeMs: number }

/**
 * The world beneath the mod: a repo at /repo whose .droid-reviews/ holds
 * `files`, and a clock at `now`. `git` is the one .git there is; `isGone`
 * makes every pid asked after a process that is no more.
 */
function world(on: On, files: Record<string, File>, now: number, { git = '/repo/.git', isGone = false } = {}) {
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('fs.stat', (_, e) => {
    if (e.path !== FOLDER) return { deny: 'ENOENT' }
    return { value: { kind: 'dir', size: 0, mtimeMs: 0, isLink: false } }
  })
  on('fs.exists', (_, e) => ({ value: e.path === git }))
  on('fs.list', () => ({
    value: Object.entries(files).map(([name, file]) => ({
      name,
      kind: 'file' as const,
      size: file.text.length,
      mtimeMs: file.mtimeMs,
      isLink: false,
    })),
  }))
  on('fs.read', (_, e) => {
    const file = files[e.path.slice(FOLDER.length + 1)]
    return file ? { value: file.text } : { deny: 'ENOENT' }
  })
  on('process.run', (_, e) => ({
    value: {
      exitCode: isGone ? 1 : 0,
      stdout: '',
      stderr: isGone ? `kill: ${e.argv.at(-1)}: No such process` : '',
      isStdoutTruncated: false,
      isStderrTruncated: false,
    },
  }))
  // What the engine draws when the mod passes: its own, empty band.
  on('ui.render', { component: 'AbovePrompt' }, ($, e) => {
    const { Text } = $.ui.resolve(e)
    return <Text>nothing of the mod's</Text>
  })
  return mock.clock(on, { now })
}

const meta = (fields: object, mtimeMs: number): File => ({
  text: JSON.stringify({ kind: 'review', model: 'glm-5.3-flash', model_name: 'GLM-5.3-Flash', round: 1, ...fields }),
  mtimeMs,
})

const FINISHED = {
  status: 'ok',
  started: '2026-10-05T18:02:29+08:00',
  finished: '2026-10-05T18:04:24+08:00',
  duration_s: 115,
  turns: 6,
}

test('a finished review waits in the band to be triaged, then says what came of it', async ($, on) => {
  const files = { 'a.json': meta(FINISHED, at('18:04:24')) }
  const clock = world(on, files, at('18:09:30'))
  await $.session.start({ cwd: '/repo/src', surface: 'terminal', isInteractive: true })
  await clock.settle()

  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...BAND, surface })
    const row = await ui.find({ text: /droid-review · GLM-5.3-Flash/ })
    expect(row?.text).toContain('✓ 1m 55s · 6 turns')
    expect(row?.text).toContain('awaiting triage for 5m...')
    await ui.unmount()
  }

  files['a.json'] = meta(
    { ...FINISHED, responses: [{ at: '2026-10-05T18:09:40+08:00', text: 'fixed  two,\nskipped one' }] },
    at('18:09:40'),
  )
  await clock.advance(70_000)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ text: /triaged/ }))?.text).toContain('triaged 1m ago: fixed two, skipped one')
})

test('a running review shows its time against the estimate and what droid is doing', async ($, on) => {
  const log = [
    '[0m01s] started glm-5.3-flash (reasoning medium) session s',
    '[0m06s] turn 1 · Skill review',
    '[0m11s] turn 2 · Execute cd /repo && git diff --stat origin/master...HEAD',
    '[0m11s] turn 2 · Read AGENTS.md',
    '[0m12s] turn 2 ↳ Execute returned in 0s',
    '[0m20s] turn 3 · Execute npm test',
  ].join('\n')
  const files = {
    'a.json': meta(FINISHED, at('18:04:24')),
    'b.json': meta({ status: 'running', started: '2026-10-05T19:00:00+08:00', pid: 4242 }, at('19:00:00')),
    'b.log': { text: log, mtimeMs: at('19:00:20') },
  }
  const clock = world(on, files, at('19:00:25'))
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await clock.settle()

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const row = await ui.find({ text: /GLM-5.3-Flash/ })
  expect(row?.text).toContain('25s / ~1m 55s')
  expect(row?.text).toContain('reading files · turn 3 · Execute npm test')

  // Quiet for half a minute with a command still out: it is the command that runs.
  await clock.advance(40_000)
  expect((await ui.find({ text: /GLM-5.3-Flash/ }))?.text).toContain('running checks for 45s · turn 3 · Execute npm test')
})

test('with nothing running or recent the band is left to the engine', async ($, on) => {
  const clock = world(on, { 'a.json': meta(FINISHED, at('18:04:24')) }, at('20:30:00'))
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await clock.settle()

  for (const surface of SURFACES) {
    const ui = await $.ui.mount({ ...BAND, surface })
    expect(await ui.find({ text: /droid-review/ })).toBeUndefined()
    expect(await ui.find({ text: "nothing of the mod's" })).toBeDefined()
    await ui.unmount()
  }
})

const RUNNING = { status: 'running', started: '2026-10-05T19:00:00+08:00', pid: 4242 }
const READING = { text: '[0m20s] turn 2 · Read x', mtimeMs: at('19:00:20') }
/** The log of a run from before the metadata, done in `seconds`. */
const legacy = (seconds: number): File => ({
  text: `[0m01s] started glm-5.3-flash (reasoning high) session abc\n[0m09s] turn 1 · Read README.md\n[0m${seconds}s] done · 9 turns · ${seconds}s\n`,
  mtimeMs: at('18:00:00'),
})

test('a half-written or foreign .json is passed over, and a log without a run\'s .json still counts toward the estimate', async ($, on) => {
  const files = {
    'junk.json': { text: '{not json', mtimeMs: at('18:00:00') },
    'junk.log': legacy(50),
    'list.json': { text: '[1, 2]', mtimeMs: at('18:00:00') },
    'old.log': legacy(70),
    'b.json': meta(RUNNING, at('19:00:00')),
    'b.log': READING,
  }
  const clock = world(on, files, at('19:00:25'))
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await clock.settle()

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ text: /droid-review/ }))?.text).toContain('25s / ~1m ')
})

test('a run whose process is gone reads as stopped', async ($, on) => {
  const files = { 'b.json': meta(RUNNING, at('19:00:00')), 'b.log': READING }
  const clock = world(on, files, at('19:00:25'), { isGone: true })
  await $.session.start({ cwd: '/repo', surface: 'terminal', isInteractive: true })
  await clock.settle()

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  const row = await ui.find({ text: /droid-review/ })
  expect(row?.text).toContain('   stopped   ')
  expect(row?.text).toContain('just now · its process is gone')
})

test('a repo inside another does not show the outer one\'s reviews', async ($, on) => {
  const files = { 'b.json': meta(RUNNING, at('19:00:00')), 'b.log': READING }
  const clock = world(on, files, at('19:00:25'), { git: '/repo/vendor/inner/.git' })
  await $.session.start({ cwd: '/repo/vendor/inner/src', surface: 'terminal', isInteractive: true })
  await clock.settle()

  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ text: /droid-review/ })).toBeUndefined()
})
