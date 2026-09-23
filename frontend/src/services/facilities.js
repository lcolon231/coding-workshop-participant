/**
 * Buildings, floors, seats, categories and engineer profiles.
 *
 * Reads are open to every signed-in user because the report form needs the
 * building, floor, seat cascade. Lists are capped at the API maximum; the
 * admin screens pass `include_inactive` and `search` on top of that. Writes
 * and the engineer endpoints are admin only.
 */
import { authedRequest, withQuery } from './api'

const BASE = '/api/facilities'
const ALL = { limit: 100 }

export function listBuildings(params = {}) {
  return authedRequest(withQuery(`${BASE}/buildings`, { ...ALL, ...params }))
}

export function listFloors(buildingId, params = {}) {
  return authedRequest(withQuery(`${BASE}/buildings/${buildingId}/floors`, { ...ALL, ...params }))
}

export function listSeats(floorId, params = {}) {
  return authedRequest(withQuery(`${BASE}/floors/${floorId}/seats`, { ...ALL, ...params }))
}

export function listCategories(params = {}) {
  return authedRequest(withQuery(`${BASE}/categories`, { ...ALL, ...params }))
}

export function getBuilding(id) {
  return authedRequest(`${BASE}/buildings/${id}`)
}

export function getFloor(id) {
  return authedRequest(`${BASE}/floors/${id}`)
}

export function getSeat(id) {
  return authedRequest(`${BASE}/seats/${id}`)
}

export function getCategory(id) {
  return authedRequest(`${BASE}/categories/${id}`)
}

// Writes. `PUT` is partial: only the fields given are sent.

export function createBuilding(body) {
  return authedRequest(`${BASE}/buildings`, { method: 'POST', body })
}

export function updateBuilding(id, changes) {
  return authedRequest(`${BASE}/buildings/${id}`, { method: 'PUT', body: changes })
}

export function deleteBuilding(id) {
  return authedRequest(`${BASE}/buildings/${id}`, { method: 'DELETE' })
}

export function createFloor(body) {
  return authedRequest(`${BASE}/floors`, { method: 'POST', body })
}

export function updateFloor(id, changes) {
  return authedRequest(`${BASE}/floors/${id}`, { method: 'PUT', body: changes })
}

export function deleteFloor(id) {
  return authedRequest(`${BASE}/floors/${id}`, { method: 'DELETE' })
}

export function createSeat(body) {
  return authedRequest(`${BASE}/seats`, { method: 'POST', body })
}

export function updateSeat(id, changes) {
  return authedRequest(`${BASE}/seats/${id}`, { method: 'PUT', body: changes })
}

export function deleteSeat(id) {
  return authedRequest(`${BASE}/seats/${id}`, { method: 'DELETE' })
}

export function createCategory(body) {
  return authedRequest(`${BASE}/categories`, { method: 'POST', body })
}

export function updateCategory(id, changes) {
  return authedRequest(`${BASE}/categories/${id}`, { method: 'PUT', body: changes })
}

export function deleteCategory(id) {
  return authedRequest(`${BASE}/categories/${id}`, { method: 'DELETE' })
}

/** Admin only: active engineers with their profile and current load. Keyed by user id. */
export function listEngineers(params = {}) {
  return authedRequest(withQuery(`${BASE}/engineers`, { ...ALL, ...params }))
}

export function updateEngineer(userId, changes) {
  return authedRequest(`${BASE}/engineers/${userId}`, { method: 'PUT', body: changes })
}
