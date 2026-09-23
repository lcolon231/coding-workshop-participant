import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { configureReadiness, readinessStatus, resetReadiness, subscribeReadiness, waitUntilReady } from './readiness'
import { jsonResponse } from '../test/helpers'

function readyz(...answers) {
  const queue = [...answers]
  return vi.fn(async () => {
    const answer = queue.length > 1 ? queue.shift() : queue[0]
    if (answer === 'down') throw new TypeError('Failed to fetch')
    if (answer === 'html') return new Response('<html>504</html>', { status: 504, headers: { 'content-type': 'text/html' } })
    return jsonResponse(answer === 'ready' ? 200 : 503, {
      status: answer === 'ready' ? 'ready' : 'not_ready',
      database: answer === 'ready',
      migrations_pending: false,
    })
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  resetReadiness()
  // The unit setup turns polling off; these tests are about the polling.
  configureReadiness({ deadlineMs: 90_000, intervalMs: 3000 })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  configureReadiness({ deadlineMs: 0, intervalMs: 0 })
})

describe('waitUntilReady', () => {
  it('resolves at once, and silently, when the API was ready all along', async () => {
    const fetch = readyz('ready')
    vi.stubGlobal('fetch', fetch)
    const seen = []
    subscribeReadiness((status) => seen.push(status))

    await expect(waitUntilReady()).resolves.toBe('ready')
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0][0]).toBe('/api/auth/readyz')
    expect(seen).toEqual([])
  })

  it('announces the wait, polls until ready, then clears it', async () => {
    vi.stubGlobal('fetch', readyz('down', 'html', 'not_ready', 'ready'))
    const seen = []
    subscribeReadiness((status) => seen.push(status.waking))

    const wait = waitUntilReady({ intervalMs: 1000 })
    await vi.advanceTimersByTimeAsync(10)
    expect(readinessStatus().waking).toBe(true)
    await vi.advanceTimersByTimeAsync(3000)
    await expect(wait).resolves.toBe('woke')
    expect(readinessStatus().waking).toBe(false)
    expect(seen).toEqual([true, false])
  })

  it('gives up at the deadline and clears the wait', async () => {
    vi.stubGlobal('fetch', readyz('not_ready'))
    const wait = waitUntilReady({ intervalMs: 1000, deadlineMs: 3500 })
    await vi.advanceTimersByTimeAsync(4000)
    await expect(wait).resolves.toBe(false)
    expect(readinessStatus().waking).toBe(false)
  })

  it('shares one wait between concurrent callers', async () => {
    const fetch = readyz('not_ready', 'ready')
    vi.stubGlobal('fetch', fetch)
    const first = waitUntilReady({ intervalMs: 1000 })
    const second = waitUntilReady({ intervalMs: 1000 })
    expect(second).toBe(first)
    await vi.advanceTimersByTimeAsync(1500)
    await expect(first).resolves.toBe('woke')
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
