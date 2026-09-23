import { authedRequest, request, withQuery } from './api'

/** Exchange credentials for a token pair. */
export function login({ email, password }) {
  return request('/api/auth/login', { method: 'POST', body: { email, password } })
}

/**
 * Self-register. Resolves with `{ message }` whether or not the address was
 * new; the API does not disclose which.
 */
export function register({ email, password, full_name, occupation, date_of_birth }) {
  return request('/api/auth/register', {
    method: 'POST',
    body: { email, password, full_name, occupation, date_of_birth },
  })
}

/** The signed-in user, including their engineer profile when they have one. */
export function fetchMe() {
  return authedRequest('/api/auth/me')
}

/** Revoke this device's refresh token. Always 204; needs no access token. */
export function logout(refreshToken) {
  return request('/api/auth/logout', { method: 'POST', body: { refresh_token: refreshToken } })
}

/** Admin only: page through users, e.g. the active engineers to assign work to. */
export function listUsers(params = {}) {
  return authedRequest(withQuery('/api/auth/users', params))
}

/** Admin only: the one place a role is chosen. Duplicate email is a 409. */
export function createUser(body) {
  return authedRequest('/api/auth/users', { method: 'POST', body })
}

export function getUser(id) {
  return authedRequest(`/api/auth/users/${id}`)
}

/** Admin only, partial. A role change or deactivation ends the target's sessions. */
export function updateUser(id, changes) {
  return authedRequest(`/api/auth/users/${id}`, { method: 'PUT', body: changes })
}

/** Admin only. A soft delete: the account is deactivated, never removed. */
export function deactivateUser(id) {
  return authedRequest(`/api/auth/users/${id}`, { method: 'DELETE' })
}
