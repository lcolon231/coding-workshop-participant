import { authedRequest, withQuery } from './api'

const BASE = '/api/incidents/notifications'

/** The caller's own notifications, newest first, with `unread_count` for the badge. */
export function listNotifications(params = {}) {
  return authedRequest(withQuery(BASE, params))
}

export function markNotificationRead(id) {
  return authedRequest(`${BASE}/${id}/read`, { method: 'POST' })
}

export function markAllNotificationsRead() {
  return authedRequest(`${BASE}/read-all`, { method: 'POST' })
}
