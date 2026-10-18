/** One run of text in a row: its colours are raw (#rrggbb), absent for the theme's own. */
export type DroidReviewsSeg = { text: string; color?: string; bg?: string; bold?: boolean }

/** One review's row in the band, keyed by the run's file name. */
export type DroidReviewsRow = { key: string; segs: DroidReviewsSeg[] }

/** A running review's bar: when it started and its estimate, in seconds; null with no history to go by. */
export type DroidReviewsRunning = { kind: 'running'; started: number; estimate: number | null }

/** A finished review's bar: what it says and the colour it is filled with. */
export type DroidReviewsEnded = { kind: 'ended'; ground: 'done' | 'red' | 'amber'; text: string }

/** A row with its bar and spinner left to be painted at any moment: null `lead` is the spinner. */
export type DroidReviewsPlan = {
  key: string
  /** Which of the band's colours it is drawn in, one of five: its model's. */
  hue: number
  lead: DroidReviewsSeg | null
  name: DroidReviewsSeg[]
  meter: DroidReviewsRunning | DroidReviewsEnded
  tail: DroidReviewsSeg[]
}

/** The band: its rows as of `now`, the last scan's time in seconds. */
export type DroidReviewsBand = { now: number; plans: DroidReviewsPlan[] }

declare module 'claude-code' {
  interface PluginState {
    'droid-reviews': { band: DroidReviewsBand }
  }
}
