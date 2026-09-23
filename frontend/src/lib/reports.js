/**
 * Shaping for the reporting dashboard: date ranges, series order and the
 * pivot that turns the sparse volume rows into continuous buckets.
 *
 * Everything here is pure so the chart components stay presentational.
 */
import { isoDate } from './format'
import { PRIORITIES, STATUSES } from './incidents'

const DAY = 24 * 60 * 60 * 1000

export const RANGE_PRESETS = [
  { days: 7, label: 'Last 7 days' },
  { days: 30, label: 'Last 30 days' },
  { days: 90, label: 'Last 90 days' },
]

export const SLA_GROUPS = [
  { value: 'priority', label: 'Priority' },
  { value: 'building', label: 'Building' },
  { value: 'category', label: 'Category' },
]

export const VOLUME_GROUPS = [
  { value: 'status', label: 'Status' },
  { value: 'priority', label: 'Priority' },
  { value: 'category', label: 'Category' },
]

export const INTERVALS = [
  { value: 'day', label: 'Daily' },
  { value: 'week', label: 'Weekly' },
]

/** Past this many series the tail folds into one, rather than inventing hues. */
export const MAX_SERIES = 7
export const OTHER = 'Other'

/** The inclusive range of `days` days ending on `to` (a date or ISO date). */
export function rangeEnding(to, days) {
  const end = new Date(to)
  const start = new Date(end.getTime() - (days - 1) * DAY)
  return { from: isoDate(start), to: isoDate(end) }
}

/** What the API assumes when no range is given: the last 30 days, ending today. */
export function defaultRange(now = new Date()) {
  return rangeEnding(now, 30)
}

/** Which preset, if any, this range is. */
export function presetFor(range, now = new Date()) {
  return RANGE_PRESETS.find((preset) => {
    const candidate = rangeEnding(now, preset.days)
    return candidate.from === range.from && candidate.to === range.to
  })
}

/**
 * The series to draw, in a fixed order with a fixed colour slot each.
 *
 * Statuses and priorities keep their domain order and their slot even when
 * some are absent, so a filter never repaints the survivors. Categories are
 * alphabetical; past `MAX_SERIES` the rest fold into "Other".
 */
export function buildSeries(groupBy, rows) {
  const present = new Set(rows.map((row) => row.group))
  const fixed = groupBy === 'status' ? STATUSES : groupBy === 'priority' ? PRIORITIES : null
  if (fixed) {
    return fixed.map((name, slot) => ({ name, slot })).filter((series) => present.has(series.name))
  }
  const names = [...present].sort((a, b) => a.localeCompare(b))
  if (names.length <= MAX_SERIES) return names.map((name, slot) => ({ name, slot }))
  const kept = names.slice(0, MAX_SERIES - 1).map((name, slot) => ({ name, slot }))
  return [...kept, { name: OTHER, slot: MAX_SERIES - 1 }]
}

/** Every bucket start between `from` and `to`, as ISO dates. Weeks start on Monday. */
export function bucketStarts(from, to, interval) {
  const start = new Date(`${from}T00:00:00Z`)
  const end = new Date(`${to}T00:00:00Z`)
  if (interval === 'week') {
    // getUTCDay: Sunday is 0. Step back to the Monday on or before `from`.
    const back = (start.getUTCDay() + 6) % 7
    start.setUTCDate(start.getUTCDate() - back)
  }
  const step = interval === 'week' ? 7 : 1
  const starts = []
  for (let at = start; at <= end; at = new Date(at.getTime() + step * DAY)) {
    starts.push(isoDate(at))
  }
  return starts
}

/**
 * The sparse `{bucket_start, group, count}` rows as one entry per bucket,
 * zero-filled, with groups outside `series` folded into "Other".
 */
export function pivotVolume(rows, { from, to, interval, series }) {
  const names = series.map((entry) => entry.name)
  const known = new Set(names)
  const buckets = new Map(
    bucketStarts(from, to, interval).map((bucket_start) => [
      bucket_start,
      { bucket_start, values: Object.fromEntries(names.map((name) => [name, 0])), total: 0 },
    ]),
  )
  for (const row of rows) {
    const bucket = buckets.get(row.bucket_start)
    if (!bucket) continue
    const name = known.has(row.group) ? row.group : OTHER
    if (!(name in bucket.values)) continue
    bucket.values[name] += row.count
    bucket.total += row.count
  }
  return [...buckets.values()]
}

const shortDate = new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', timeZone: 'UTC' })

/** "22 Sept" for a bucket start. */
export function bucketLabel(isoDay) {
  return shortDate.format(new Date(`${isoDay}T00:00:00Z`))
}

/** The open backlog: everything in the window that is not Closed. */
export function openBacklog(summary) {
  return summary.by_status
    .filter((entry) => entry.key !== 'Closed')
    .reduce((sum, entry) => sum + entry.count, 0)
}

export function countOf(entries, key) {
  return entries.find((entry) => entry.key === key)?.count ?? 0
}

/** How many rows one export request asks for: the API's page ceiling. */
export const EXPORT_PAGE = 100

const CSV_COLUMNS = [
  ['id', (incident) => incident.id],
  ['title', (incident) => incident.title],
  ['status', (incident) => incident.status],
  ['priority', (incident) => incident.priority],
  ['building', (incident, names) => names.get(incident.building_id) ?? incident.building_id],
  ['reporter', (incident) => incident.reporter?.full_name ?? ''],
  ['assignee', (incident) => incident.assignee?.full_name ?? ''],
  ['reported_at', (incident) => incident.created_at],
  ['acknowledged_at', (incident) => incident.acknowledged_at ?? ''],
  ['resolved_at', (incident) => incident.resolved_at ?? ''],
  ['closed_at', (incident) => incident.closed_at ?? ''],
]

/** One CSV field: quoted when it holds a comma, a quote or a line break. */
export function csvCell(value) {
  const text = value === null || value === undefined ? '' : String(value)
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

/**
 * The incidents as CSV with a header row, building ids resolved to names
 * through `buildingNames` (a Map of id to name). CRLF line ends, as RFC 4180
 * and spreadsheets expect.
 */
export function incidentsCsv(incidents, buildingNames = new Map()) {
  const header = CSV_COLUMNS.map(([name]) => name).join(',')
  const lines = incidents.map((incident) =>
    CSV_COLUMNS.map(([, pick]) => csvCell(pick(incident, buildingNames))).join(','),
  )
  return [header, ...lines].join('\r\n') + '\r\n'
}

/**
 * Every incident `fetchPage` can reach, one page after another, oldest
 * first so the file reads top to bottom. `fetchPage` takes `{limit, offset}`
 * and returns a `Page`.
 */
export async function collectAll(fetchPage) {
  const items = []
  let offset = 0
  let total = Infinity
  while (offset < total) {
    const page = await fetchPage({ limit: EXPORT_PAGE, offset })
    items.push(...page.items)
    total = page.total
    if (page.items.length === 0) break
    offset += page.items.length
  }
  return items
}

/** "incidents-2026-08-25-to-2026-09-23.csv" */
export function exportFilename(range) {
  return `incidents-${range.from}-to-${range.to}.csv`
}
