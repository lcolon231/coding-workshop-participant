/**
 * Domain vocabulary shared by the incident screens.
 *
 * The enum values are the API's display strings, so nothing is translated on
 * the way in or out.
 */

import { formatDuration } from './format'

export const STATUSES = ['Open', 'In Progress', 'Blocked', 'Resolved', 'Closed']
export const PRIORITIES = ['Low', 'Medium', 'High', 'Critical']

/** Which palette key colours each status chip. Neutral where nothing is happening. */
export const STATUS_COLOR = {
  Open: 'default',
  'In Progress': 'primary',
  Blocked: 'warning',
  Resolved: 'success',
  Closed: 'default',
}

export const PRIORITY_COLOR = {
  Low: 'default',
  Medium: 'default',
  High: 'warning',
  Critical: 'error',
}

/**
 * The API's `sla_state`, judged when the row was served: open work against
 * the clock, or finished work against its target. Colour follows urgency;
 * what is finished and fine stays quiet.
 */
export const SLA_COLOR = {
  on_track: 'default',
  at_risk: 'warning',
  breached: 'error',
  met: 'success',
  missed: 'error',
}

/** The words on the chip: a countdown while open, a verdict once finished. */
export function slaLabel(incident, now = Date.now()) {
  const state = incident.sla_state
  if (state === 'met') return 'Met target'
  if (state === 'missed') return 'Missed target'
  const remaining = (new Date(incident.due_at).getTime() - now) / 1000
  if (state === 'breached' || remaining < 0) return `Overdue by ${formatDuration(-remaining)}`
  return `Due in ${formatDuration(remaining)}`
}

/** Transitions that move work forward get the filled button; the rest are outlined. */
export const FORWARD_TRANSITIONS = new Set(['In Progress', 'Resolved', 'Closed'])

export const SORT_OPTIONS = [
  { value: 'created_at:desc', label: 'Newest first' },
  { value: 'created_at:asc', label: 'Oldest first' },
  { value: 'priority:desc', label: 'Priority, high to low' },
  { value: 'due_at:asc', label: 'Due soonest' },
  { value: 'status:asc', label: 'Status' },
  { value: 'title:asc', label: 'Title, A to Z' },
]

export const PAGE_SIZE = 25

export function isStaff(user) {
  return user?.role === 'Facility Admin' || user?.role === 'Engineer'
}

export function isAdmin(user) {
  return user?.role === 'Facility Admin'
}

/** Whether this user may ask an admin to raise the priority of this incident. */
export function canRequestEscalation(user, incident, escalations) {
  if (!user || !incident) return false
  const involved = incident.reporter_id === user.id || incident.assignee_id === user.id
  const active = !['Resolved', 'Closed'].includes(incident.status)
  const pending = (escalations ?? []).some((item) => item.status === 'Pending')
  return involved && active && incident.priority !== 'Critical' && !pending
}
