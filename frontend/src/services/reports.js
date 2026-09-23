/**
 * Admin reports over incidents.
 *
 * All three take `from`, `to` (inclusive dates, default the last 30 days,
 * at most 366 days apart) and an optional `building_id`.
 */
import { authedRequest, withQuery } from './api'

const BASE = '/api/incidents/reports'

/** Counts by status, by priority, and the open backlog by age bucket. */
export function fetchSummary(params = {}) {
  return authedRequest(withQuery(`${BASE}/summary`, params))
}

/** Per group (`group_by`: priority, building or category): time to acknowledge and resolve. */
export function fetchSla(params = {}) {
  return authedRequest(withQuery(`${BASE}/sla`, params))
}

/** Incidents created per `interval` (day or week), split by `group_by`. Sparse rows. */
export function fetchVolume(params = {}) {
  return authedRequest(withQuery(`${BASE}/volume`, params))
}
