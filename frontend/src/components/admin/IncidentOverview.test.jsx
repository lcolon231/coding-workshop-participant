import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import IncidentOverview from './IncidentOverview'
import { ADMIN, calls, jsonResponse, renderSignedIn, signIn, stubApi } from '../../test/helpers'

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
    { engineer_id: 'u-eng', engineer: 'Hank Vance', is_active: true, assigned_count: 5, open_count: 1, completed_count: 4, mean_resolve_seconds: 8100 },
    { engineer_id: 'u-eng2', engineer: 'Ida Lupin', is_active: false, assigned_count: 2, open_count: 2, completed_count: 0, mean_resolve_seconds: null },
  ],
}

function routes(overrides = {}) {
  return [
    ['GET', '/api/incidents/reports/buildings', overrides.buildings ?? (() => jsonResponse(200, BUILDINGS))],
    ['GET', '/api/incidents/reports/engineers', overrides.engineers ?? (() => jsonResponse(200, ENGINEERS))],
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
  it('ranks buildings by incidents, still open and critical over the last 30 days', async () => {
    const fetch = stubApi(routes())
    renderOverview()

    const buildings = await screen.findByRole('region', { name: 'Buildings' })
    await within(buildings).findByRole('region', { name: 'Most incidents' })
    expect(calls(fetch)).toEqual(
      expect.arrayContaining([
        'GET /api/incidents/reports/buildings?from=2026-08-25&to=2026-09-23',
        'GET /api/incidents/reports/engineers?from=2026-08-25&to=2026-09-23',
      ]),
    )
    expect(names(buildings, 'Most incidents')).toEqual(['Headquarters7', 'Riverside Annex3'])
    expect(names(buildings, 'Still open')).toEqual(['Riverside Annex3', 'Headquarters2'])
    expect(names(buildings, 'Critical')).toEqual(['Headquarters1', 'Riverside Annex0'])
    expect(screen.getByRole('button', { name: 'Last 30 days' })).toHaveAttribute('aria-pressed', 'true')
  })

  it("shows each engineer's workload and who completed the most", async () => {
    stubApi(routes())
    renderOverview()

    const engineers = await screen.findByRole('region', { name: 'Engineers' })
    await within(engineers).findByRole('table', { name: 'Engineer workload' })
    expect(names(engineers, 'Completed')).toEqual(['Hank Vance4', 'Ida Lupin0'])
    expect(names(engineers, 'Open workload')[0]).toBe('Ida Lupin2')

    const table = within(engineers).getByRole('table', { name: 'Engineer workload' })
    const hank = within(table).getByText('Hank Vance').closest('tr')
    expect(within(hank).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['Hank Vance', '5', '1', '4', '2h 15m'])
    const ida = within(table).getByText('Ida Lupin').closest('tr')
    expect(within(ida).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['Ida LupinDeactivated', '2', '2', '0', '—'])
  })

  it('reloads both halves for another range', async () => {
    const fetch = stubApi(routes())
    renderOverview()
    await screen.findByRole('region', { name: 'Most incidents' })

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
    expect(await screen.findByRole('table', { name: 'Engineer workload' })).toBeInTheDocument()
  })
})
