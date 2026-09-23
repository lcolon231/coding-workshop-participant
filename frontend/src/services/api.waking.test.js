import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, isWakingError, request } from './api'
import { configureReadiness, readinessStatus, resetReadiness } from './readiness'
import { jsonResponse } from '../test/helpers'

/**
 * A fetch that answers `readyz` from one queue and everything else from
 * another, so a test can script "the API was asleep, then woke up".
 */
function stub({ readyz, api }) {
  const readyQueue = [...readyz]
  const apiQueue = [...api]
  const fetch = vi.fn(async (input, init = {}) => {
    const queue = String(input).endsWith('/readyz') ? readyQueue : apiQueue
    const answer = queue.length > 1 ? queue.shift() : queue[0]
    if (answer === 'down') throw new TypeError('Failed to fetch')
    if (answer === 'html504') {
      return new Response('<html>Gateway timeout</html>', { status: 504, headers: { 'content-type': 'text/html' } })
    }
    if (answer === 'ready') return jsonResponse(200, { status: 'ready', database: true, migrations_pending: false })
    if (answer === 'not_ready') return jsonResponse(503, { status: 'not_ready', database: false, migrations_pending: null })
    if (answer === 'internal') return jsonResponse(500, { error: 'internal_error', message: 'Something went wrong.' })
    if (answer === 'ok') return jsonResponse(200, { ok: true, method: init.method ?? 'GET' })
    throw new Error(`unscripted answer ${answer}`)
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// Real timers, milliseconds apart: hashing a request body finishes on the
// real event loop, which a fake clock never yields to.
beforeEach(() => {
  resetReadiness()
  configureReadiness({ deadlineMs: 400, intervalMs: 10 })
})

afterEach(() => {
  vi.unstubAllGlobals()
  configureReadiness({ deadlineMs: 0, intervalMs: 0 })
})

describe('request while the database wakes', () => {
  it('classifies edge timeouts, service failures and no answer as possibly waking', () => {
    for (const status of [0, 500, 502, 503, 504]) {
      expect(isWakingError(new ApiError({ status, error: 'x', message: 'x' }))).toBe(true)
    }
    for (const status of [400, 401, 403, 404, 409]) {
      expect(isWakingError(new ApiError({ status, error: 'x', message: 'x' }))).toBe(false)
    }
    expect(isWakingError(new Error('plain'))).toBe(false)
  })

  it('waits for readiness after a CloudFront 504 and then retries a GET', async () => {
    const fetch = stub({ readyz: ['not_ready', 'not_ready', 'ready'], api: ['html504', 'ok'] })
    const pending = request('/api/incidents')
    await pause(5)
    expect(readinessStatus().waking).toBe(true)
    await expect(pending).resolves.toEqual({ ok: true, method: 'GET' })
    expect(readinessStatus().waking).toBe(false)
    const paths = fetch.mock.calls.map(([input]) => String(input))
    expect(paths.at(0)).toBe('/api/incidents')
    expect(paths.at(-1)).toBe('/api/incidents')
    expect(paths.slice(1, -1).every((path) => path === '/api/auth/readyz')).toBe(true)
    expect(paths.length).toBeGreaterThanOrEqual(4)
  })

  it('retries a POST only when it never reached the server', async () => {
    stub({ readyz: ['not_ready', 'ready'], api: ['down', 'ok'] })
    await expect(request('/api/incidents', { method: 'POST', body: { title: 'x' } })).resolves.toEqual({
      ok: true,
      method: 'POST',
    })
  })

  it('refuses to replay a POST the server may have acted on, once the API is back', async () => {
    stub({ readyz: ['not_ready', 'ready'], api: ['html504', 'ok'] })
    const failure = await request('/api/incidents', { method: 'POST', body: { title: 'x' } }).catch((e) => e)
    expect(failure).toBeInstanceOf(ApiError)
    expect(failure.error).toBe('database_waking')
    expect(failure.status).toBe(504)
    expect(failure.message).toMatch(/waking up/)
  })

  it('surfaces the original failure when the API never becomes ready', async () => {
    stub({ readyz: ['not_ready'], api: ['internal'] })
    const failure = await request('/api/incidents').catch((e) => e)
    expect(failure).toBeInstanceOf(ApiError)
    expect(failure.error).toBe('internal_error')
    expect(failure.status).toBe(500)
    expect(readinessStatus().waking).toBe(false)
  })

  it('treats a failure while the API was ready all along as final, without a retry', async () => {
    const fetch = stub({ readyz: ['ready'], api: ['internal', 'ok'] })
    const failure = await request('/api/incidents').catch((e) => e)
    expect(failure).toBeInstanceOf(ApiError)
    expect(failure.status).toBe(500)
    expect(readinessStatus().waking).toBe(false)
    expect(fetch.mock.calls.map(([input]) => String(input))).toEqual(['/api/incidents', '/api/auth/readyz'])
  })

  it('leaves a genuine refusal alone', async () => {
    const fetch = stub({ readyz: ['ready'], api: [] })
    fetch.mockImplementationOnce(async () => jsonResponse(404, { error: 'not_found', message: 'No such incident.' }))
    const failure = await request('/api/incidents/nope').catch((e) => e)
    expect(failure.status).toBe(404)
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
