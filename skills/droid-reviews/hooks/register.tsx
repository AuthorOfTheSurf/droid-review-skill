// droid reviews in a band above the prompt: one row per review running in
// this repo. This file reads .droid-reviews/ once a second; rows.ts says what a
// row is, and band.tsx paints the rows every frame on a surface that runs a
// Client (elsewhere this file paints them once a second, still). With nothing
// to show the band is left as it was.

import { atom, read, update } from 'claude-code'
import type { EngineInterface, FsEntry, Register } from 'claude-code'

import type { DroidReviewsBand } from '../types'
import { history, paint, plan } from './rows'
import type { LogEnds, Meta, Run } from './rows'

const NONE: DroidReviewsBand = { now: 0, plans: [] }
const shown = atom({ plugin: 'droid-reviews', key: 'band' } as const, NONE)

const TICK_MS = 1000
const LOOK_AGAIN_TICKS = 10 // no .droid-reviews/ yet: look for one this often
const ALIVE_FOR_MS = 3000 // how long an answer about a pid stands
const TAIL = 8192 // the end of a log a row is worked out from

/** A value read from a file, kept until the file changes. */
type Kept<T> = { stamp: string; value: T }
const stampOf = (entry: FsEntry) => `${entry.mtimeMs}:${entry.size}`

const parent = (dir: string) => dir.slice(0, Math.max(1, dir.lastIndexOf('/')))

/** The .droid-reviews/ of the repo `start` is in: the nearest at or above it, no higher than the repo's top. */
async function findReviews($: EngineInterface, start: string): Promise<string | null> {
  for (let dir = start; ; dir = parent(dir)) {
    const folder = `${dir === '/' ? '' : dir}/.droid-reviews`
    const stat = await $.fs.stat(folder).catch(() => undefined)
    if (stat?.kind === 'dir') return folder
    if ((await $.fs.exists(`${dir}/.git`)) || parent(dir) === dir) return null
  }
}

/** The last whole lines of a log. */
function tail(text: string): string[] {
  const lines = text.slice(-TAIL).split('\n')
  return (text.length > TAIL ? lines.slice(1) : lines).filter(Boolean)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const metas = new Map<string, Kept<Meta | null>>()
    const logs = new Map<string, Kept<string>>()
    const alive = new Map<string, { at: number; isAlive: boolean }>()
    let folder: string | null = null
    let ticks = 0
    let isScanning = false
    let drawn = '[]'

    /** A file's text, read again only when the file changed; null when it cannot be read. */
    async function text(kept: Map<string, Kept<string>>, entry: FsEntry): Promise<string | null> {
      const had = kept.get(entry.name)
      if (had?.stamp === stampOf(entry)) return had.value
      const value = await $.fs.read(`${folder}/${entry.name}`).catch(() => null)
      if (value !== null) kept.set(entry.name, { stamp: stampOf(entry), value })
      return value
    }

    async function isAlive(pid: Meta['pid'], nowMs: number): Promise<boolean> {
      const id = String(pid)
      if (!/^\d+$/.test(id)) return true // unknowable: do not call it dead
      const had = alive.get(id)
      if (had && nowMs - had.at < ALIVE_FOR_MS) return had.isAlive
      // Exists but not ours (EPERM) also exits 1: only "No such process" is dead.
      const answer = await $.process.run(['kill', '-0', id])
        .then(r => r.exitCode === 0 || !/no such process/i.test(r.stderr))
        .catch(() => true)
      alive.set(id, { at: nowMs, isAlive: answer })
      return answer
    }

    async function scan(): Promise<DroidReviewsBand> {
      if (folder === null) {
        if (ticks++ % LOOK_AGAIN_TICKS !== 0) return NONE
        folder = await findReviews($, e.cwd)
        if (folder === null) return NONE
      }
      const entries = await $.fs.list(folder).catch(() => null)
      if (entries === null) {
        folder = null // deleted: deleting old reviews is safe
        return NONE
      }
      const files = new Map(entries.filter(entry => entry.kind === 'file').map(entry => [entry.name, entry]))
      const nowMs = await $.clock.now()

      const runs: Run[] = []
      await Promise.all(
        [...files.values()].map(async entry => {
          if (!entry.name.endsWith('.json')) return
          let had = metas.get(entry.name)
          if (had?.stamp !== stampOf(entry)) {
            // Half-written or not ours: skipped until it changes.
            const parsed: unknown = await $.fs.read(`${folder}/${entry.name}`).then(JSON.parse).catch(() => null)
            const isRun = typeof parsed === 'object' && parsed !== null && Boolean((parsed as Meta).status)
            had = { stamp: stampOf(entry), value: isRun ? (parsed as Meta) : null }
            metas.set(entry.name, had)
          }
          if (had.value === null) return
          const name = entry.name.slice(0, -5)
          const log = files.get(`${name}.log`)
          const isRunning = had.value.status === 'running'
          runs.push({
            name,
            meta: had.value,
            logAt: log ? log.mtimeMs / 1000 : null,
            isAlive: isRunning ? await isAlive(had.value.pid, nowMs) : false,
            lines: isRunning && log ? tail((await text(logs, log)) ?? '') : [],
          })
        }),
      )

      // The estimate a running bar is measured against also counts runs older
      // than the metadata: logs with no .json of a run beside them.
      const orphans: LogEnds[] = []
      if (runs.some(run => run.meta.status === 'running')) {
        const named = new Set(runs.map(run => run.name))
        for (const entry of files.values()) {
          if (!entry.name.endsWith('.log') || named.has(entry.name.slice(0, -4))) continue
          const lines = ((await text(logs, entry)) ?? '').split('\n').filter(Boolean)
          if (lines.length) orphans.push({ first: lines[0]!, last: lines.at(-1)! })
        }
      }
      return { now: nowMs / 1000, plans: plan(runs, history(runs, orphans), nowMs / 1000) }
    }

    async function tick(): Promise<void> {
      if (isScanning) return
      isScanning = true
      try {
        const band = await scan()
        const drawing = JSON.stringify(band.plans)
        // Written when a row changed, and while one runs, so its time stays
        // true: a band of finished rows redraws once a minute.
        if (drawing !== drawn || band.plans.some(p => p.meter.kind === 'running')) {
          await update($, shown, () => band)
          drawn = drawing
        }
      } catch {
        // A band must never take the session down with it.
      } finally {
        isScanning = false
      }
    }

    void tick()
    $.clock.every(TICK_MS, () => void tick())

    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const band = await read($, shown)
    if (e.props.hasSurvey || band.plans.length === 0) return next(e)

    const elements = $.ui.resolve(e)
    const { Box, Text } = elements
    if ('Client' in elements) {
      const { Client } = elements
      return (
        <Box flexDirection="column" width={e.props.bodyColumns} marginTop={1}>
          <Client key="band" module="./band.tsx" props={band} width="100%" />
        </Box>
      )
    }

    return (
      <Box flexDirection="column" width={e.props.bodyColumns} marginTop={1}>
        {band.plans.map(p => paint(p, band.now, null)).map(row => (
          <Text wrap="truncate-end">
            {row.segs.map(seg => (
              <Text
                {...(seg.color ? { color: seg.color } : {})}
                {...(seg.bg ? { backgroundColor: seg.bg } : {})}
                {...(seg.bold ? { bold: true } : {})}
              >
                {seg.text}
              </Text>
            ))}
          </Text>
        ))}
      </Box>
    )
  })
}
