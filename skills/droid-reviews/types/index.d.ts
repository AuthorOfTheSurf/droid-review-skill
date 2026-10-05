/** One run of text in a row: its colours are raw (#rrggbb), absent for the theme's own. */
export type DroidReviewsSeg = { text: string; color?: string; bg?: string; bold?: boolean }

/** One review's row in the band, keyed by the run's file name. */
export type DroidReviewsRow = { key: string; segs: DroidReviewsSeg[] }

declare module 'claude-code' {
  interface PluginState {
    'droid-reviews': { rows: DroidReviewsRow[] }
  }
}
