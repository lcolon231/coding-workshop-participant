import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, authedRequest } from './api'
import { readSession } from './session'
import { calls, jsonResponse, signIn, stubApi } from '../test/helpers'

const FRESH = { access_token: 'access-2', refresh_token: 'refresh-2', token_type: 'bearer', expires_in: 1800 }

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('authedRequest', () => {
  it('attaches the bearer token', async () => {
    signIn()
    const fetch = stubApi([['GET', '/api/x', () => jsonResponse(200, { ok: true })]])
    await expect(authedRequest('/api/x')).resolves.toEqual({ ok: true })
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer access-1')
  })

  it('refuses without a session, without calling the API', async () => {
    const fetch = stubApi([])
    const err = await authedRequest('/api/x').catch((e) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect(err.error).toBe('session_ended')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('refreshes once on a 401 and retries with the new token', async () => {
    signIn()
    const fetch = stubApi([
      [
        'GET',
        '/api/x',
        ({ init }) =>
          init.headers.Authorization === 'Bearer access-2'
            ? jsonResponse(200, { ok: true })
            : jsonResponse(401, { error: 'token_expired', message: 'Expired.' }),
      ],
      ['POST', '/api/auth/refresh', ({ body }) => {
        expect(body).toEqual({ refresh_token: 'refresh-1' })
        return jsonResponse(200, FRESH)
      }],
    ])
    await expect(authedRequest('/api/x')).resolves.toEqual({ ok: true })
    expect(calls(fetch)).toEqual(['GET /api/x', 'POST /api/auth/refresh', 'GET /api/x'])
    expect(readSession().accessToken).toBe('access-2')
  })

  it('shares one refresh between concurrent 401s', async () => {
    signIn()
    const fetch = stubApi([
      [
        'GET',
        /^\/api\/(x|y)$/,
        ({ init }) =>
          init.headers.Authorization === 'Bearer access-2'
            ? jsonResponse(200, { ok: true })
            : jsonResponse(401, { error: 'token_expired', message: 'Expired.' }),
      ],
      ['POST', '/api/auth/refresh', () => jsonResponse(200, FRESH)],
    ])
    await Promise.all([authedRequest('/api/x'), authedRequest('/api/y')])
    expect(calls(fetch).filter((c) => c.includes('refresh'))).toHaveLength(1)
  })

  it('ends the session when the refresh is refused', async () => {
    signIn()
    stubApi([
      ['GET', '/api/x', () => jsonResponse(401, { error: 'token_expired', message: 'Expired.' })],
      ['POST', '/api/auth/refresh', () => jsonResponse(401, { error: 'refresh_token_reused', message: 'Reused.' })],
    ])
    const err = await authedRequest('/api/x').catch((e) => e)
    expect(err.error).toBe('session_ended')
    expect(readSession()).toBeNull()
  })

  it('keeps the session when the refresh cannot reach the server', async () => {
    signIn()
    stubApi([
      ['GET', '/api/x', () => jsonResponse(401, { error: 'token_expired', message: 'Expired.' })],
      ['POST', '/api/auth/refresh', () => Promise.reject(new TypeError('Failed to fetch'))],
    ])
    const err = await authedRequest('/api/x').catch((e) => e)
    expect(err.error).toBe('network_error')
    expect(readSession()).not.toBeNull()
  })
})
