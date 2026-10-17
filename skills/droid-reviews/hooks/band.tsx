// The band painted every frame, on the surface's own clock: register.tsx hands
// it the rows once a second and this keeps the time between, so a bar moves
// and a spinner turns at FRAME_MS and not only when the rows are read again.

import type { ClientModule, ClientSurface } from 'claude-code'

import type { DroidReviewsBand, DroidReviewsRunning } from '../types'
import { FINISH_S, filledAt, paint } from './rows'

const FRAME_MS = 16 // sixty a second; a frame that comes out the same as the last writes nothing to the terminal
const CATCH_UP = 0.2 // of the time the clock is behind, how much a frame makes up: behind is caught up in a few frames, not in one jump

/**
 * One instance's time, held in its state so it goes with the instance: its own
 * between the rows it is handed, and when each row it saw running ended.
 */
type Clock = {
  band: DroidReviewsBand
  t: number
  /** The `now` of the rows last handed over. */
  told: number
  /** How far behind the rows' time the clock was when they came, not yet made up. */
  behind: number
  was: Record<string, DroidReviewsRunning>
  ended: Record<string, { at: number; from: number }>
}

/** Takes new rows: their `now` says how far the clock fell behind on frames the surface dropped, and each row that stopped running starts its finish. */
function hand(clock: Clock, band: DroidReviewsBand): void {
  clock.band = band
  if (band.now !== clock.told) {
    clock.told = band.now
    clock.behind = Math.max(0, band.now - clock.t)
    if (clock.behind > 2) {
      clock.t = band.now // long gone (a sleep, a stall): no catching up on that
      clock.behind = 0
    }
  }
  for (const p of band.plans) {
    const before = clock.was[p.key]
    if (before && p.meter.kind === 'ended' && !clock.ended[p.key]) clock.ended[p.key] = { at: clock.t, from: filledAt(before, clock.t) }
  }
  clock.was = Object.fromEntries(band.plans.flatMap(p => (p.meter.kind === 'running' ? [[p.key, p.meter]] : [])))
}

function step(clock: Clock, surface: ClientSurface<Clock>): void {
  const gain = clock.behind * CATCH_UP
  clock.behind -= gain
  clock.t += FRAME_MS / 1000 + gain
  for (const [key, e] of Object.entries(clock.ended)) if (clock.t - e.at >= FINISH_S) delete clock.ended[key]
  const isMoving = clock.band.plans.some(p => p.meter.kind === 'running') || Object.keys(clock.ended).length > 0
  if (isMoving) surface.setState({ ...clock })
}

const Band: ClientModule<DroidReviewsBand, Clock> = (band, surface) => {
  let clock = surface.state
  if (!clock) {
    clock = { band, t: band.now, told: band.now, behind: 0, was: {}, ended: {} }
    surface.setState(clock)
    surface.every(FRAME_MS, () => step(surface.state ?? clock!, surface))
  }
  hand(clock, band)

  const { Box, Text } = surface.elements
  const at = clock.t
  const ended = clock.ended
  return (
    <Box flexDirection="column">
      {band.plans.map(p => (
        <Text wrap="truncate-end">
          {paint(p, at, { ended: ended[p.key] ?? null }).segs.map(seg => (
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
}

export default Band
