import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, request } from './api'
import { jsonResponse } from '../test/helpers'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('request', () => {
  it('sends JSON and returns the parsed body', async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    vi.stubGlobal('fetch', fetch)

    await expect(request('/api/x', { method: 'POST', body: { a: 1 } })).resolves.toEqual({
      ok: true,
    })
    const [, init] = fetch.mock.calls[0]
    expect(init.headers['Content-Type']).toBe('application/json')
    expect(init.body).toBe('{"a":1}')
  })

  it('hashes the body for CloudFront-signed origin requests', async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, {}))
    vi.stubGlobal('fetch', fetch)

    await request('/api/x', { method: 'POST', body: { a: 1 } })
    const [, init] = fetch.mock.calls[0]
    // sha256('{"a":1}')
    expect(init.headers['x-amz-content-sha256']).toBe(
      '015abd7f5cc57a2dd94b7590f04ad8084273905ee33ec5cebeae62276a97f862',
    )
  })

  it('sends no payload hash without a body', async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, {}))
    vi.stubGlobal('fetch', fetch)

    await request('/api/x')
    const [, init] = fetch.mock.calls[0]
    expect(init.headers).not.toHaveProperty('x-amz-content-sha256')
    expect(init.body).toBeUndefined()
  })

  it('still sends the request where Web Crypto is unavailable', async () => {
    // An insecure HTTP origin (LocalStack) exposes no crypto.subtle.
    vi.stubGlobal('crypto', {})
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, {}))
    vi.stubGlobal('fetch', fetch)

    await request('/api/x', { method: 'POST', body: { a: 1 } })
    const [, init] = fetch.mock.calls[0]
    expect(init.headers).not.toHaveProperty('x-amz-content-sha256')
    expect(init.body).toBe('{"a":1}')
  })

  it('resolves null on 204', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(request('/api/x', { method: 'DELETE' })).resolves.toBeNull()
  })

  it('raises the envelope on a non-2xx status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(400, {
          error: 'validation_error',
          message: 'Request validation failed.',
          details: [{ field: 'email', message: 'bad' }],
          request_id: 'abc',
        }),
      ),
    )
    const err = await request('/api/x').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(400)
    expect(err.error).toBe('validation_error')
    expect(err.details).toEqual([{ field: 'email', message: 'bad' }])
    expect(err.requestId).toBe('abc')
  })

  it('refuses a non-JSON body even with a 200 status', async () => {
    // CloudFront rewrites an API 404 to `200 index.html`.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('<!doctype html>', { status: 200, headers: { 'content-type': 'text/html' } }),
      ),
    )
    const err = await request('/api/x').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.error).toBe('unexpected_response')
  })

  it('reports a network failure in plain words', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    const err = await request('/api/x').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(0)
    expect(err.message).toMatch(/could not reach the server/i)
  })
})
