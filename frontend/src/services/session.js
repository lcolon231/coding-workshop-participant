/**
 * The signed-in session, kept for the lifetime of the tab.
 *
 * `AuthProvider` subscribes to changes so a refresh rotation or a sign-out
 * anywhere in the client is reflected in the UI without a page reload.
 */

const KEY = 'acme.session'

const listeners = new Set()

function notify() {
  const session = readSession()
  for (const listener of listeners) listener(session)
}

export function readSession() {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

/** Store a token pair. Returns the session as it will be read back. */
export function saveSession(tokens) {
  const session = {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    expiresAt: Date.now() + tokens.expires_in * 1000,
  }
  try {
    sessionStorage.setItem(KEY, JSON.stringify(session))
  } catch {
    // Storage unavailable (private window, blocked site data): the user
    // stays signed in until the page reloads.
  }
  notify()
  return session
}

export function clearSession() {
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // Nothing was stored, so there is nothing to clear.
  }
  notify()
}

/** Be told whenever the session is saved or cleared. Returns an unsubscribe. */
export function subscribeSession(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
