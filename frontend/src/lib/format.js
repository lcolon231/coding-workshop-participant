/** Date and text formatting, in the viewer's locale. */

const absolute = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' })
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })

const UNITS = [
  ['year', 365 * 24 * 60 * 60],
  ['month', 30 * 24 * 60 * 60],
  ['week', 7 * 24 * 60 * 60],
  ['day', 24 * 60 * 60],
  ['hour', 60 * 60],
  ['minute', 60],
]

/** "22 Sept 2026, 14:05" */
export function formatDateTime(iso) {
  if (!iso) return ''
  return absolute.format(new Date(iso))
}

/** "3 hours ago", "yesterday", "just now". */
export function formatRelative(iso, now = Date.now()) {
  if (!iso) return ''
  const seconds = Math.round((new Date(iso).getTime() - now) / 1000)
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit)
  }
  return 'just now'
}

const dateOnly = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' })

/** "22 Sept 2026" for a date or an ISO date string; dates are calendar days, so UTC. */
export function formatDate(value) {
  if (!value) return ''
  return dateOnly.format(new Date(value))
}

/** `YYYY-MM-DD` in UTC, the form the API takes for a date. */
export function isoDate(date) {
  return new Date(date).toISOString().slice(0, 10)
}

/** "45s", "12m", "2h 15m", "3d 4h". Nothing measured is an em dash. */
export function formatDuration(seconds) {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return '—'
  const total = Math.max(0, Math.round(seconds))
  if (total < 60) return `${total}s`
  const minutes = Math.floor(total / 60)
  if (minutes < 60) return `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const restMinutes = minutes % 60
  if (hours < 24) return restMinutes ? `${hours}h ${restMinutes}m` : `${hours}h`
  const days = Math.floor(hours / 24)
  const restHours = hours % 24
  return restHours ? `${days}d ${restHours}h` : `${days}d`
}

/** A 0..1 ratio as "83%"; nothing measured is an em dash. */
export function formatPercent(ratio) {
  if (ratio === null || ratio === undefined || !Number.isFinite(ratio)) return '—'
  return `${Math.round(ratio * 100)}%`
}

/** "Eve Employee" to "EE", for an avatar. */
export function initials(name) {
  return String(name ?? '')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')
}
