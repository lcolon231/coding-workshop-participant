import { expect, test } from '@playwright/test'

/**
 * The dev proxy forwards `/api` unrewritten to the backend (T75, T97).
 *
 * An empty login body is the cheapest proof: only the real service answers
 * it with the API's own 400 envelope. A misrouted request would come back as
 * Vite's `index.html` (200, HTML) or a connection error, never this.
 */
test('the Vite proxy hands /api to the backend, unrewritten', async ({ request }) => {
  const response = await request.post('/api/auth/login', { data: {} })

  expect(response.status()).toBe(400)
  expect(response.headers()['content-type']).toContain('application/json')
  const body = await response.json()
  expect(body.error).toBe('validation_error')
  expect(body.details.map((detail) => detail.field).sort()).toEqual(['email', 'password'])
  expect(response.headers()['x-request-id']).toBeTruthy()
})

test('the health routes of every service are reachable through the proxy', async ({ request }) => {
  for (const service of ['auth', 'incidents', 'facilities']) {
    const response = await request.get(`/api/${service}/healthz`)
    expect(response.status(), service).toBe(200)
    expect(response.headers()['content-type']).toContain('application/json')
  }
})
