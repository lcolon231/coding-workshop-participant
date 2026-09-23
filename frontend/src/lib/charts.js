/**
 * Chart colour lookups over the theme's `palette.chart` tokens.
 *
 * Slots are assigned in a fixed order and never cycled, so a series keeps
 * its colour whatever else is on screen. Through `theme.vars` the values are
 * CSS variables, so a chart follows the light or dark scheme by itself.
 */

/** The categorical order: adjacent pairs stay distinct under colour-vision deficiency. */
export const SERIES_SLOTS = ['violet', 'orange', 'aqua', 'yellow', 'magenta', 'green', 'blue', 'red']

function palette(theme) {
  return (theme.vars ?? theme).palette.chart
}

export function seriesColor(theme, slot) {
  return palette(theme).series[SERIES_SLOTS[slot % SERIES_SLOTS.length]]
}

/** The one hue for magnitude: bars that only compare size. */
export function sequentialColor(theme) {
  return palette(theme).sequential
}
