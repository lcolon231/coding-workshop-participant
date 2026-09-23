/**
 * Minimal JSON client for the ACME API.
 *
 * `request` is the bare transport: the error envelope and the content-type
 * guard. `authedRequest` adds the bearer token and, on a 401, rotates the
 * refresh token once and retries. Concurrent 401s share one rotation, because
 * replaying an already-retired refresh token revokes the whole family.
 */

import { clearSession, readSession, saveSession } from './session'

const NETWORK_MESSAGE = 'Could not reach the server. Check your connection and try again.'
const NOT_JSON_MESSAGE = 'The server returned an unexpected response. Try again in a moment.'
const SIGNED_OUT_MESSAGE = 'Your session has ended. Sign in again to continue.'

/** A failed request, carrying the API's flat error envelope. */
export class ApiError extends Error {
  constructor({ status, error, message, details = [], requestId = null }) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.error = error
    this.details = details
    this.requestId = requestId
  }
}

/**
 * Hex SHA-256 of a request body.
 *
 * On AWS the API sits behind CloudFront, which signs each origin request to
 * the Lambda function URLs (SigV4). Lambda rejects unsigned payloads, so a
 * request with a body must carry the body's own hash in `x-amz-content-sha256`.
 * Returns null where Web Crypto is unavailable (an insecure HTTP origin, which
 * only happens under LocalStack, where there is no CloudFront to satisfy).
 */
export async function payloadHash(text) {
  const subtle = globalThis.crypto?.subtle
  if (!subtle) return null
  const digest = await subtle.digest('SHA-256', new TextEncoder().encode(text))
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
}

/** Serialise query parameters, dropping empty ones. */
export function withQuery(path, params = {}) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    query.set(key, String(value))
  }
  const encoded = query.toString()
  return encoded ? `${path}?${encoded}` : path
}

/**
 * Send a request and return the parsed JSON body.
 *
 * Resolves with `null` on 204. Rejects with an ApiError for a network
 * failure, a non-JSON response, or any non-2xx status.
 */
export async function request(path, { method = 'GET', body, token } = {}) {
  const headers = { Accept: 'application/json' }
  const payload = body === undefined ? undefined : JSON.stringify(body)
  if (payload !== undefined) {
    headers['Content-Type'] = 'application/json'
    const hash = await payloadHash(payload)
    if (hash) headers['x-amz-content-sha256'] = hash
  }
  if (token) headers.Authorization = `Bearer ${token}`

  let response
  try {
    response = await fetch(path, { method, headers, body: payload })
  } catch {
    throw new ApiError({ status: 0, error: 'network_error', message: NETWORK_MESSAGE })
  }

  const requestId = response.headers.get('x-request-id')
  if (response.status === 204) return null

  // CloudFront rewrites an API 404 to `200 index.html`. Without this guard a
  // misrouted call would "succeed" with an HTML document as its body.
  const contentType = response.headers.get('content-type') ?? ''
  if (!contentType.includes('application/json')) {
    throw new ApiError({
      status: response.status,
      error: 'unexpected_response',
      message: NOT_JSON_MESSAGE,
      requestId,
    })
  }

  const data = await response.json()
  if (!response.ok) {
    throw new ApiError({
      status: response.status,
      error: data.error ?? 'unknown_error',
      message: data.message ?? 'Something went wrong. Try again.',
      details: Array.isArray(data.details) ? data.details : [],
      requestId: data.request_id ?? requestId,
    })
  }
  return data
}

let rotation = null

function signedOut(requestId = null) {
  return new ApiError({ status: 401, error: 'session_ended', message: SIGNED_OUT_MESSAGE, requestId })
}

/**
 * Exchange the refresh token for a new pair, once, however many callers ask.
 *
 * When the stored session already differs from the one the caller saw, another
 * request has rotated it; reuse that instead of presenting a retired token.
 */
function refreshSession(stale) {
  const current = readSession()
  if (current && current.refreshToken !== stale.refreshToken) return Promise.resolve(current)
  if (!rotation) {
    rotation = request('/api/auth/refresh', {
      method: 'POST',
      body: { refresh_token: stale.refreshToken },
    })
      .then((tokens) => saveSession(tokens))
      .catch((err) => {
        // A network failure says nothing about the session; only the API can end it.
        if (err instanceof ApiError && err.status === 0) throw err
        clearSession()
        throw signedOut(err.requestId)
      })
      .finally(() => {
        rotation = null
      })
  }
  return rotation
}

/** `request`, with the bearer token attached and a single refresh-and-retry on 401. */
export async function authedRequest(path, options = {}) {
  const session = readSession()
  if (!session) throw signedOut()
  try {
    return await request(path, { ...options, token: session.accessToken })
  } catch (err) {
    if (!(err instanceof ApiError) || err.status !== 401) throw err
    const fresh = await refreshSession(session)
    return request(path, { ...options, token: fresh.accessToken })
  }
}
