import { authedRequest, withQuery } from './api'

const BASE = '/api/incidents'

export function listIncidents(params = {}) {
  return authedRequest(withQuery(BASE, params))
}

export function getIncident(id) {
  return authedRequest(`${BASE}/${id}`)
}

export function createIncident(body) {
  return authedRequest(BASE, { method: 'POST', body })
}

/** Partial update. Only the fields given are sent; `null` clears a clearable one. */
export function updateIncident(id, changes) {
  return authedRequest(`${BASE}/${id}`, { method: 'PUT', body: changes })
}

/** The only way status changes. `body` is `{ target_status, ...required fields }`. */
export function transitionIncident(id, body) {
  return authedRequest(`${BASE}/${id}/transition`, { method: 'POST', body })
}

export function listHistory(id, params = {}) {
  return authedRequest(withQuery(`${BASE}/${id}/history`, { limit: 100, ...params }))
}

export function listNotes(id, params = {}) {
  return authedRequest(withQuery(`${BASE}/${id}/notes`, { limit: 100, ...params }))
}

export function createNote(id, { body, visibility }) {
  return authedRequest(`${BASE}/${id}/notes`, { method: 'POST', body: { body, visibility } })
}

export function listIncidentEscalations(id, params = {}) {
  return authedRequest(withQuery(`${BASE}/${id}/escalations`, { limit: 100, ...params }))
}

export function requestEscalation(id, reason) {
  return authedRequest(`${BASE}/${id}/escalations`, { method: 'POST', body: { reason } })
}
