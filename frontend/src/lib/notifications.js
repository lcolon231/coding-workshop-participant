/**
 * Phrasing for notifications.
 *
 * The API sends the kind and the facts, not a sentence, so the wording lives
 * here and can change without a migration.
 */

/** How often the bell asks for news while the tab is visible, in milliseconds. */
export const POLL_INTERVAL_MS = 60_000

/** How many recent notifications the bell's menu shows. */
export const MENU_LIMIT = 10

/** One line saying what happened, for the bell's menu. */
export function describeNotification({ kind, actor, incident_title: title }) {
  const name = actor?.full_name
  const quoted = `“${title}”`
  switch (kind) {
    case 'Assigned':
      return name ? `${name} assigned you ${quoted}` : `You were assigned ${quoted}`
    case 'Reported':
      return name ? `${name} reported ${quoted}` : `New incident: ${quoted}`
    case 'Resolved':
      return name ? `${name} resolved ${quoted}` : `${quoted} was resolved`
    case 'Closed':
      return name ? `${name} closed ${quoted}` : `${quoted} was closed`
    default:
      return quoted
  }
}
