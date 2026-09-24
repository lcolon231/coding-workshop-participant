import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import IncidentOverview from './IncidentOverview'
import { ADMIN, calls, jsonResponse, page, renderSignedIn, signIn, stubApi } from '../../test/helpers'

const BUILDINGS = {
  from: '2026-08-25',
  to: '2026-09-23',
  rows: [
    { building_id: 'b-hq', building: 'Headquarters', count: 7, open_count: 2, critical_count: 1 },
    { building_id: 'b-rva', building: 'Riverside Annex', count: 3, open_count: 3, critical_count: 0 },
  ],
}

const ENGINEERS = {
  from: '2026-08-25',
  to: '2026-09-23',
  rows: [
    { engineer_id: 'u-eng', engineer: 'Hank Vance', specialty: 'HVAC', is_active: true, assigned_count: 5, open_count: 1, completed_count: 4, mean_resolve_seconds: 8100 },
    { engineer_id: 'u-eng2', engineer: 'Ida Lupin', specialty: 'Electrical', is_active: false, assigned_count: 2, open_count: 2, completed_count: 0, mean_resolve_seconds: null },
  ],
}

const AVAILABLE = page([
  {
    user_id: 'u-eng3',
    user: { id: 'u-eng3', full_name: 'Jo Marsh', role: 'Engineer' },
    specialty: 'Plumbing',
    max_concurrent_incidents: 5,
    is_available: true,
    open_assignments: 0,
  },
  {
    user_id: 'u-eng',
    user: { id: 'u-eng', full_name: 'Hank Vance', role: 'Engineer' },
    specialty: 'HVAC',
    max_concurrent_incidents: 3,
    is_available: true,
    open_assignments: 3,
  },
])

function routes(overrides = {}) {
  return [
    ['GET', '/api/incidents/reports/buildings', overrides.buildings ?? (() => jsonResponse(200, BUILDINGS))],
    ['GET', '/api/incidents/reports/engineers', overrides.engineers ?? (() => jsonResponse(200, ENGINEERS))],
    ['GET', '/api/facilities/engineers', overrides.available ?? (() => jsonResponse(200, AVAILABLE))],
  ]
}

function renderOverview() {
  signIn()
  return renderSignedIn(<IncidentOverview />, { path: '/', user: ADMIN })
}

function names(region, title) {
  return within(within(region).getByRole('region', { name: title }))
    .getAllByRole('listitem')
    .map((item) => item.textContent)
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-23T10:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('IncidentOverview', () => {
  it('charts each building as finished and open, busiest first, over the last 30 days', async () => {
    const fetch = stubApi(routes())
    renderOverview()

    const buildings = await screen.findByRole('region', { name: 'Buildings' })
    const chart = await within(buildings).findByRole('img', { name: 'Incidents per building, finished and still open' })
    expect(calls(fetch)).toEqual(
      expect.arrayContaining([
        'GET /api/incidents/reports/buildings?from=2026-08-25&to=2026-09-23',
        'GET /api/incidents/reports/engineers?from=2026-08-25&to=2026-09-23',
      ]),
    )
    expect(Array.from(chart.querySelectorAll('path[aria-label]')).map((rect) => rect.getAttribute('aria-label'))).toEqual([
      'Headquarters: 7 incidents, 70%',
      'Riverside Annex: 3 incidents, 30%',
    ])
    expect(names(buildings, 'Critical')).toEqual(['Headquarters1100%'])
    expect(screen.getByRole('button', { name: 'Last 30 days' })).toHaveAttribute('aria-pressed', 'true')

    await userEvent.click(within(buildings).getByRole('button', { name: 'View as table' }))
    const table = within(buildings).getByRole('table', { name: 'Building' })
    const hq = within(table).getByText('Headquarters').closest('tr')
    expect(within(hq).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['Headquarters', '5', '2', '7', '1'])
  })

  it("charts each engineer's completed and open work with their role, and tables the detail", async () => {
    stubApi(routes())
    renderOverview()

    const engineers = await screen.findByRole('region', { name: 'Engineers' })
    const chart = await within(engineers).findByRole('img', { name: 'Incidents per engineer, completed and still open' })
    const legend = within(engineers).getByRole('list', { name: 'Slices' })
    expect(within(legend).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Hank VanceHVAC571%', 'Ida LupinElectrical229%'])
    expect(Array.from(chart.querySelectorAll('path[aria-label]')).map((rect) => rect.getAttribute('aria-label'))).toEqual([
      'Hank Vance (HVAC): 5 incidents, 71%',
      'Ida Lupin (Electrical): 2 incidents, 29%',
    ])

    await userEvent.click(within(engineers).getByRole('button', { name: 'View as table' }))
    const table = within(engineers).getByRole('table', { name: 'Engineer workload' })
    expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual([
      'Engineer', 'Role', 'Assigned', 'Open', 'Completed', 'Resolved, mean',
    ])
    const hank = within(table).getByText('Hank Vance').closest('tr')
    expect(within(hank).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['Hank Vance', 'HVAC', '5', '1', '4', '2h 15m'])
    const ida = within(table).getByText('Ida Lupin').closest('tr')
    expect(within(ida).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['Ida LupinDeactivated', 'Electrical', '2', '2', '0', '—'])
  })

  it('lists who is available right now, with role and load, regardless of the range', async () => {
    const fetch = stubApi(routes())
    renderOverview()

    const available = await screen.findByRole('region', { name: 'Available now' })
    const list = await within(available).findByRole('list', { name: 'Available engineers' })
    expect(within(list).getAllByRole('listitem').map((item) => item.textContent)).toEqual([
      'Jo MarshPlumbing0 of 5 open',
      'Hank VanceHVAC3 of 3 open, at capacity',
    ])
    expect(calls(fetch)).toContain('GET /api/facilities/engineers?limit=100&is_available=true&sort=open_assignments&order=asc')

    await userEvent.click(screen.getByRole('button', { name: 'Last 7 days' }))
    await screen.findByRole('img', { name: /Incidents per building/ })
    expect(calls(fetch).filter((call) => call.startsWith('GET /api/facilities/engineers'))).toHaveLength(1)
  })

  it('says when nobody is available', async () => {
    stubApi(routes({ available: () => jsonResponse(200, page([])) }))
    renderOverview()

    expect(await screen.findByRole('heading', { name: 'Nobody is available' })).toBeInTheDocument()
  })

  it('reloads both halves for another range', async () => {
    const fetch = stubApi(routes())
    renderOverview()

    await screen.findByRole('img', { name: /Incidents per building/ })
    await userEvent.click(screen.getByRole('button', { name: 'Last 7 days' }))
    await waitFor(() =>
      expect(calls(fetch)).toEqual(
        expect.arrayContaining([
          'GET /api/incidents/reports/buildings?from=2026-09-17&to=2026-09-23',
          'GET /api/incidents/reports/engineers?from=2026-09-17&to=2026-09-23',
        ]),
      ),
    )
    expect(screen.getByRole('button', { name: 'Last 7 days' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('says when there is nothing, and keeps one half when the other fails', async () => {
    let attempts = 0
    stubApi(
      routes({
        buildings: () => jsonResponse(200, { ...BUILDINGS, rows: BUILDINGS.rows.map((row) => ({ ...row, count: 0, open_count: 0, critical_count: 0 })) }),
        engineers: () =>
          (attempts += 1) === 1 ? jsonResponse(500, { error: 'internal_error', message: 'Database unavailable.' }) : jsonResponse(200, ENGINEERS),
      }),
    )
    renderOverview()

    expect(await screen.findByRole('heading', { name: 'No incidents in this range' })).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable.')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('img', { name: /Incidents per engineer/ })).toBeInTheDocument()
  })
})
