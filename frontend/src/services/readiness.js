/**
 * Knows whether the API can answer, and waits while it wakes.
 *
 * On AWS the database pauses after a quiet period and takes up to a minute
 * to resume. During that time a request fails at the edge (a CloudFront 504
 * or 502), at the service (500 or 503) or never connects at all. None of that
 * is the caller's fault, so the API client polls `readyz` until the database
 * answers and then retries. This module owns the polling and publishes its
 * progress so the screen can say what is happening instead of spinning.
 */

const READYZ = '/api/auth/readyz'
export const POLL_INTERVAL_MS = 3000
export const WAKE_DEADLINE_MS = 90_000

const listeners = new Set()
let status = { waking: false, since: null }
let waiting = null
let defaults = { deadlineMs: WAKE_DEADLINE_MS, intervalMs: POLL_INTERVAL_MS }

/** Change how long and how often to poll; the unit test setup turns polling off. */
export function configureReadiness(options) {
  defaults = { ...defaults, ...options }
}

/** The current `{ waking, since }`; `since` is when the wait began. */
export function readinessStatus() {
  return status
}

/** Be told whenever the status changes; returns the unsubscribe. */
export function subscribeReadiness(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function publish(next) {
  status = next
  for (const listener of listeners) listener(status)
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

/** One probe: true when the service reports itself ready. */
export async function probeReady() {
  try {
    const response = await fetch(READYZ, { headers: { Accept: 'application/json' } })
    if (!response.ok) return false
    const contentType = response.headers.get('content-type') ?? ''
    if (!contentType.includes('application/json')) return false
    const body = await response.json()
    return body.status === 'ready'
  } catch {
    return false
  }
}

/**
 * Resolve `'ready'` when the API was ready all along, `'woke'` once it comes
 * back after being unready, or `false` at the deadline.
 *
 * The first probe is silent: a request that failed for some other reason
 * finds the API already ready, nothing is shown, and the caller knows the
 * failure was not the database. Only when the API is really not ready does
 * the wait announce itself. Concurrent callers share one wait.
 */
export function waitUntilReady(options = {}) {
  if (waiting) return waiting
  const { deadlineMs, intervalMs } = { ...defaults, ...options }
  waiting = (async () => {
    if (await probeReady()) return 'ready'
    const started = Date.now()
    publish({ waking: true, since: started })
    try {
      while (Date.now() - started < deadlineMs) {
        await sleep(intervalMs)
        if (await probeReady()) return 'woke'
      }
      return false
    } finally {
      publish({ waking: false, since: null })
    }
  })().finally(() => {
    waiting = null
  })
  return waiting
}

/** Test hook: forget any wait in progress and any listeners. */
export function resetReadiness() {
  waiting = null
  listeners.clear()
  status = { waking: false, since: null }
}
