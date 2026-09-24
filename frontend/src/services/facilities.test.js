import { afterEach, describe, expect, it, vi } from 'vitest'
import * as facilities from './facilities'
import { saveSession } from './session'
import { jsonResponse } from '../test/helpers'

/** Every wrapper, with the request it must produce. */
const CALLS = [
  ['listBuildings', [{ include_inactive: true }], 'GET', '/api/facilities/buildings?limit=100&include_inactive=true'],
  ['listFloors', ['b-1'], 'GET', '/api/facilities/buildings/b-1/floors?limit=100'],
  ['listSeats', ['f-1'], 'GET', '/api/facilities/floors/f-1/seats?limit=100'],
  ['listCategories', [], 'GET', '/api/facilities/categories?limit=100'],
  ['getBuilding', ['b-1'], 'GET', '/api/facilities/buildings/b-1'],
  ['getFloor', ['f-1'], 'GET', '/api/facilities/floors/f-1'],
  ['getSeat', ['s-1'], 'GET', '/api/facilities/seats/s-1'],
  ['getCategory', ['c-1'], 'GET', '/api/facilities/categories/c-1'],
  ['createBuilding', [{ code: 'HQ' }], 'POST', '/api/facilities/buildings', { code: 'HQ' }],
  ['updateBuilding', ['b-1', { name: 'HQ' }], 'PUT', '/api/facilities/buildings/b-1', { name: 'HQ' }],
  ['deleteBuilding', ['b-1'], 'DELETE', '/api/facilities/buildings/b-1'],
  ['createFloor', [{ level: 1 }], 'POST', '/api/facilities/floors', { level: 1 }],
  ['updateFloor', ['f-1', { name: 'Ground' }], 'PUT', '/api/facilities/floors/f-1', { name: 'Ground' }],
  ['deleteFloor', ['f-1'], 'DELETE', '/api/facilities/floors/f-1'],
  ['createSeat', [{ code: '1-01' }], 'POST', '/api/facilities/seats', { code: '1-01' }],
  ['updateSeat', ['s-1', { label: 'Window' }], 'PUT', '/api/facilities/seats/s-1', { label: 'Window' }],
  ['deleteSeat', ['s-1'], 'DELETE', '/api/facilities/seats/s-1'],
  ['createCategory', [{ name: 'HVAC' }], 'POST', '/api/facilities/categories', { name: 'HVAC' }],
  ['updateCategory', ['c-1', { is_active: false }], 'PUT', '/api/facilities/categories/c-1', { is_active: false }],
  ['deleteCategory', ['c-1'], 'DELETE', '/api/facilities/categories/c-1'],
  ['listEngineers', [{ is_available: true }], 'GET', '/api/facilities/engineers?limit=100&is_available=true'],
  ['updateEngineer', ['u-1', { max_concurrent_incidents: 3 }], 'PUT', '/api/facilities/engineers/u-1', { max_concurrent_incidents: 3 }],
]

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('facilities service', () => {
  it.each(CALLS)('%s sends %s %s', async (name, args, method, url, body) => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }))
    vi.stubGlobal('fetch', fetch)
    saveSession({ access_token: 'access', refresh_token: 'refresh', expires_in: 1800 })

    await expect(facilities[name](...args)).resolves.toEqual({ ok: true })

    const [calledUrl, init] = fetch.mock.calls[0]
    expect(String(calledUrl)).toBe(url)
    expect(init.method ?? 'GET').toBe(method)
    expect(init.headers['X-Acme-Authorization']).toBe('Bearer access')
    if (body) expect(JSON.parse(init.body)).toEqual(body)
    else expect(init.body).toBeUndefined()
  })
})
