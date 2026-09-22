/**
 * Buildings, floors, seats and categories.
 *
 * Reads are open to every signed-in user because the report form needs the
 * building, floor, seat cascade. Lists are capped at the API maximum.
 */
import { authedRequest, withQuery } from './api'

const BASE = '/api/facilities'
const ALL = { limit: 100 }

export function listBuildings() {
  return authedRequest(withQuery(`${BASE}/buildings`, ALL))
}

export function listFloors(buildingId) {
  return authedRequest(withQuery(`${BASE}/buildings/${buildingId}/floors`, ALL))
}

export function listSeats(floorId) {
  return authedRequest(withQuery(`${BASE}/floors/${floorId}/seats`, ALL))
}

export function listCategories() {
  return authedRequest(withQuery(`${BASE}/categories`, ALL))
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
