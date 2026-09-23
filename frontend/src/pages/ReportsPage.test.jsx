import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ReportsPage from './ReportsPage'
import { ADMIN, ENGINEER, calls, incidentFixture, jsonResponse, page, renderSignedIn, signIn, stubApi } from '../test/helpers'

const SUMMARY = {
  from: '2026-08-25',
  to: '2026-09-23',
  total: 10,
  by_status: [
    { key: 'Open', count: 3 },
    { key: 'In Progress', count: 2 },
    { key: 'Blocked', count: 1 },
    { key: 'Resolved', count: 1 },
    { key: 'Closed', count: 3 },
  ],
  by_priority: [
    { key: 'Low', count: 2 },
    { key: 'Medium', count: 4 },
    { key: 'High', count: 3 },
    { key: 'Critical', count: 1 },
  ],
  backlog_by_age: [
    { key: '<1d', count: 2 },
    { key: '1-3d', count: 3 },
    { key: '3-7d', count: 1 },
    { key: '>7d', count: 1 },
  ],
}

const SLA = {
  from: '2026-08-25',
  to: '2026-09-23',
  group_by: 'priority',
  targets: [
    { priority: 'Critical', target_seconds: 14400 },
    { priority: 'High', target_seconds: 86400 },
    { priority: 'Medium', target_seconds: 259200 },
    { priority: 'Low', target_seconds: 604800 },
  ],
  rows: [
    {
      group: 'Critical',
      count: 1,
      resolved_count: 1,
      mean_ack_seconds: 600,
      p90_ack_seconds: 600,
      mean_resolve_seconds: 8100,
      p90_resolve_seconds: 8100,
      within_target_ratio: 1,
    },
    {
      group: 'High',
      count: 3,
      resolved_count: 0,
      mean_ack_seconds: null,
      p90_ack_seconds: null,
      mean_resolve_seconds: null,
      p90_resolve_seconds: null,
      within_target_ratio: null,
    },
  ],
}

const VOLUME = {
  from: '2026-08-25',
  to: '2026-09-23',
  interval: 'day',
  group_by: 'status',
  rows: [
    { bucket_start: '2026-09-21', group: 'Open', count: 2 },
    { bucket_start: '2026-09-21', group: 'Closed', count: 1 },
    { bucket_start: '2026-09-23', group: 'Open', count: 4 },
  ],
}

const BUILDINGS = [
  { id: 'b-hq', code: 'HQ', name: 'Headquarters', address: null, is_active: true },
  { id: 'b-rva', code: 'RVA', name: 'Riverside Annex', address: null, is_active: true },
]

const BY_BUILDING = {
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
    {
      engineer_id: 'u-eng',
      engineer: 'Hank Vance',
      is_active: true,
      assigned_count: 5,
      open_count: 1,
      completed_count: 4,
      mean_resolve_seconds: 8100,
    },
    {
      engineer_id: 'u-eng2',
      engineer: 'Ida Lupin',
      is_active: false,
      assigned_count: 2,
      open_count: 2,
      completed_count: 0,
      mean_resolve_seconds: null,
    },
  ],
}

const INCIDENTS = [
  incidentFixture({ id: 'inc-1', title: 'Aircon dripping', building_id: 'b-hq', created_at: '2026-09-22T09:12:00Z' }),
  incidentFixture({
    id: 'inc-2',
    title: 'Lift stuck',
    status: 'Resolved',
    priority: 'High',
    building_id: 'b-rva',
    assignee_id: ENGINEER.id,
    assignee: ENGINEER,
    created_at: '2026-09-20T08:00:00Z',
    resolved_at: '2026-09-21T10:30:00Z',
  }),
]

function routes(overrides = {}) {
  return [
    ['GET', '/api/incidents/reports/summary', overrides.summary ?? (() => jsonResponse(200, SUMMARY))],
    ['GET', '/api/incidents/reports/sla', overrides.sla ?? (() => jsonResponse(200, SLA))],
    ['GET', '/api/incidents/reports/volume', overrides.volume ?? (() => jsonResponse(200, VOLUME))],
    ['GET', '/api/incidents/reports/buildings', overrides.buildings ?? (() => jsonResponse(200, BY_BUILDING))],
    ['GET', '/api/incidents/reports/engineers', overrides.engineers ?? (() => jsonResponse(200, ENGINEERS))],
    ['GET', '/api/incidents', overrides.incidents ?? (() => jsonResponse(200, page(INCIDENTS)))],
    ['GET', '/api/facilities/buildings', () => jsonResponse(200, page(BUILDINGS))],
  ]
}

function renderReports({ initialEntries } = {}) {
  signIn()
  return renderSignedIn(<ReportsPage />, { path: '/reports', initialEntries, user: ADMIN })
}

function region(name) {
  return screen.getByRole('region', { name })
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-23T10:00:00Z'))
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('ReportsPage', () => {
  it('asks for the last 30 days and shows the headline numbers', async () => {
    const fetch = stubApi(routes())
    renderReports()

    expect(await screen.findByText('10')).toBeInTheDocument()
    expect(calls(fetch)).toEqual(
      expect.arrayContaining([
        'GET /api/incidents/reports/summary?from=2026-08-25&to=2026-09-23',
        'GET /api/incidents/reports/sla?from=2026-08-25&to=2026-09-23&group_by=priority',
        'GET /api/incidents/reports/volume?from=2026-08-25&to=2026-09-23&interval=day&group_by=status',
      ]),
    )
    const summary = region('Summary')
    const tile = (name) => within(summary).getByRole('group', { name })
    expect(tile('Open backlog')).toHaveTextContent('7')
    expect(tile('Resolved or closed')).toHaveTextContent('4')
    expect(tile('Resolved or closed')).toHaveTextContent('40%')
    expect(tile('Critical')).toHaveTextContent('1')
    const byAge = within(summary).getByRole('region', { name: 'Open backlog by age' })
    expect(within(byAge).getByText('1-3d')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Last 30 days' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('renders response times with formatted durations and the targets', async () => {
    stubApi(routes())
    renderReports()

    const table = await screen.findByRole('table', { name: 'Response times' })
    const critical = within(table).getByText('Critical').closest('tr')
    expect(within(critical).getAllByText('10m')).toHaveLength(2)
    expect(within(critical).getAllByText('2h 15m')).toHaveLength(2)
    expect(within(critical).getByText('100%')).toBeInTheDocument()
    const high = within(table).getByText('High').closest('tr')
    expect(within(high).getAllByText('—')).toHaveLength(5)
    expect(screen.getByText(/Critical 4h, High 1d, Medium 3d, Low 7d/)).toBeInTheDocument()
  })

  it('draws the volume with a legend and swaps to a table', async () => {
    stubApi(routes())
    renderReports()

    const chart = await screen.findByRole('img', { name: 'Incidents reported per day, split by status' })
    const legend = within(region('Volume')).getByRole('list', { name: 'Series' })
    expect(within(legend).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Open', 'Closed'])
    // Bucket labels follow the viewer's locale, so only the day and count are pinned.
    expect(within(chart).getByLabelText(/\b21\b.*: 3 incidents/)).toBeInTheDocument()
    expect(within(chart).getByLabelText(/\b22\b.*: 0 incidents/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'View as table' }))
    const table = screen.getByRole('table', { name: 'Incidents per bucket' })
    expect(within(table).getAllByRole('row')).toHaveLength(31)
    const last = within(table).getAllByRole('row').at(-1)
    const cells = within(last).getAllByRole('cell').map((cell) => cell.textContent)
    expect(cells[0]).toMatch(/\b23\b/)
    expect(cells.slice(1)).toEqual(['4', '0', '4'])
  })

  it('puts the preset, the building and the split in the URL and the requests', async () => {
    const fetch = stubApi(routes())
    renderReports()
    await screen.findByText('10')

    await userEvent.click(screen.getByRole('button', { name: 'Last 7 days' }))
    await waitFor(() =>
      expect(calls(fetch)).toContain('GET /api/incidents/reports/summary?from=2026-09-17&to=2026-09-23'),
    )

    await userEvent.selectOptions(await screen.findByLabelText('Building'), 'b-rva')
    await waitFor(() =>
      expect(calls(fetch)).toContain(
        'GET /api/incidents/reports/volume?from=2026-09-17&to=2026-09-23&building_id=b-rva&interval=day&group_by=status',
      ),
    )
    expect(await screen.findByText(/in Riverside Annex/)).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Split by'), 'category')
    await userEvent.selectOptions(screen.getByLabelText('Per'), 'week')
    await waitFor(() =>
      expect(calls(fetch)).toContain(
        'GET /api/incidents/reports/volume?from=2026-09-17&to=2026-09-23&building_id=b-rva&interval=week&group_by=category',
      ),
    )
    await userEvent.selectOptions(screen.getByLabelText('By'), 'building')
    await waitFor(() =>
      expect(calls(fetch)).toContain(
        'GET /api/incidents/reports/sla?from=2026-09-17&to=2026-09-23&building_id=b-rva&group_by=building',
      ),
    )
  })

  it('warns about an inverted range instead of asking the API', async () => {
    const fetch = stubApi(routes())
    renderReports()
    await screen.findByText('10')
    const before = calls(fetch).length

    fireEvent.change(screen.getByLabelText('From'), { target: { value: '2026-09-30' } })
    expect(await screen.findByText('The start of the range is after its end.')).toBeInTheDocument()
    expect(calls(fetch)).toHaveLength(before)
  })

  it('keeps the other sections when one report fails, and retries it', async () => {
    let attempts = 0
    stubApi(
      routes({
        sla: () =>
          (attempts += 1) === 1
            ? jsonResponse(500, { error: 'internal_error', message: 'Database unavailable.' })
            : jsonResponse(200, SLA),
      }),
    )
    renderReports()

    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable.')
    expect(await screen.findByText('10')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: /Incidents reported per day/ })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('table', { name: 'Response times' })).toBeInTheDocument()
  })

  it('says when the range is empty rather than drawing nothing', async () => {
    stubApi(
      routes({
        summary: () =>
          jsonResponse(200, {
            ...SUMMARY,
            total: 0,
            by_status: SUMMARY.by_status.map((entry) => ({ ...entry, count: 0 })),
          }),
        sla: () => jsonResponse(200, { ...SLA, rows: [] }),
        volume: () => jsonResponse(200, { ...VOLUME, rows: [] }),
        buildings: () => jsonResponse(200, { ...BY_BUILDING, rows: BY_BUILDING.rows.map((row) => ({ ...row, count: 0, open_count: 0, critical_count: 0 })) }),
        incidents: () => jsonResponse(200, page([])),
      }),
    )
    renderReports()

    expect(await screen.findAllByRole('heading', { name: 'No incidents in this range' })).toHaveLength(5)
    expect(screen.getByRole('button', { name: 'Download CSV' })).toBeDisabled()
  })

  it('ranks buildings by incidents, still open and critical', async () => {
    stubApi(routes())
    renderReports()

    const buildings = await screen.findByRole('region', { name: 'Buildings' })
    const names = (title) =>
      within(within(buildings).getByRole('region', { name: title }))
        .getAllByRole('listitem')
        .map((item) => item.textContent)
    expect(names('Most incidents')).toEqual(['Headquarters7', 'Riverside Annex3'])
    expect(names('Still open')).toEqual(['Riverside Annex3', 'Headquarters2'])
    expect(names('Critical')).toEqual(['Headquarters1', 'Riverside Annex0'])
  })

  it('shows each engineer\'s workload and who completed the most', async () => {
    stubApi(routes())
    renderReports()

    const engineers = await screen.findByRole('region', { name: 'Engineers' })
    const completed = within(engineers).getByRole('region', { name: 'Completed' })
    expect(within(completed).getAllByRole('listitem').map((item) => item.textContent)).toEqual(['Hank Vance4', 'Ida Lupin0'])
    const workload = within(engineers).getByRole('region', { name: 'Open workload' })
    expect(within(workload).getAllByRole('listitem')[0]).toHaveTextContent('Ida Lupin2')

    const table = within(engineers).getByRole('table', { name: 'Engineer workload' })
    const hank = within(table).getByText('Hank Vance').closest('tr')
    expect(within(hank).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['Hank Vance', '5', '1', '4', '2h 15m'])
    const ida = within(table).getByText('Ida Lupin').closest('tr')
    expect(ida).toHaveTextContent('Deactivated')
    expect(within(ida).getAllByRole('cell').map((cell) => cell.textContent)).toEqual(['Ida LupinDeactivated', '2', '2', '0', '—'])
  })

  it('lists every incident in the range with its building, and pages through them', async () => {
    const fetch = stubApi(
      routes({
        incidents: () => jsonResponse(200, page(INCIDENTS, { total: 40, limit: 25 })),
      }),
    )
    renderReports()

    const table = await screen.findByRole('table', { name: 'All incidents' })
    expect(calls(fetch)).toContain(
      'GET /api/incidents?created_from=2026-08-25&created_to=2026-09-23&sort=created_at&order=desc&limit=25&offset=0',
    )
    const lift = within(table).getByRole('link', { name: 'Lift stuck' }).closest('tr')
    expect(lift).toHaveTextContent('Riverside Annex')
    expect(lift).toHaveTextContent('Hank Vance')
    expect(within(lift).getAllByRole('cell')[1]).toHaveTextContent('Resolved')
    expect(within(lift).getAllByRole('cell').at(-1)).toHaveTextContent(/\b21\b.*2026/)
    const aircon = within(table).getByRole('link', { name: 'Aircon dripping' }).closest('tr')
    expect(aircon).toHaveTextContent('Unassigned')
    expect(within(aircon).getAllByRole('cell').at(-1)).toHaveTextContent('—')
    expect(screen.getByText('Showing 1–2 of 40')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Go to page 2' }))
    await waitFor(() =>
      expect(calls(fetch)).toContain(
        'GET /api/incidents?created_from=2026-08-25&created_to=2026-09-23&sort=created_at&order=desc&limit=25&offset=25',
      ),
    )
    // Changing the window goes back to the first page.
    await userEvent.click(screen.getByRole('button', { name: 'Last 7 days' }))
    await waitFor(() =>
      expect(calls(fetch)).toContain(
        'GET /api/incidents?created_from=2026-09-17&created_to=2026-09-23&sort=created_at&order=desc&limit=25&offset=0',
      ),
    )
  })

  it('exports every page of the range as one CSV file', async () => {
    const saved = []
    // jsdom has no object URLs; keep the real constructor and add the two statics.
    vi.stubGlobal(
      'URL',
      class extends URL {
        static createObjectURL = vi.fn((blob) => {
          saved.push(blob)
          return 'blob:incidents'
        })
        static revokeObjectURL = vi.fn()
      },
    )
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const fetch = stubApi(
      routes({
        incidents: ({ url }) => {
          const offset = Number(url.searchParams.get('offset'))
          const items = offset === 0 ? Array.from({ length: 100 }, (_, i) => incidentFixture({ id: `inc-${i}`, title: `Incident ${i}` })) : [INCIDENTS[1]]
          return jsonResponse(200, page(items, { total: 101, limit: 100, offset }))
        },
      }),
    )
    renderReports()

    const download = screen.getByRole('button', { name: 'Download CSV' })
    await waitFor(() => expect(download).toBeEnabled())
    await userEvent.click(download)
    expect(await screen.findByRole('status')).toHaveTextContent('Exported 101 incidents.')
    expect(calls(fetch)).toContain(
      'GET /api/incidents?created_from=2026-08-25&created_to=2026-09-23&sort=created_at&order=asc&limit=100&offset=100',
    )
    expect(click).toHaveBeenCalledTimes(1)
    const text = await saved[0].text()
    expect(text.split('\r\n')[0]).toBe('id,title,status,priority,building,reporter,assignee,reported_at,acknowledged_at,resolved_at,closed_at')
    expect(text).toContain('inc-2,Lift stuck,Resolved,High,Riverside Annex,Eve Employee,Hank Vance,2026-09-20T08:00:00Z,,2026-09-21T10:30:00Z,')
    click.mockRestore()
  })

  it('reports an export that failed instead of saving a partial file', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    let listed = 0
    stubApi(
      routes({
        incidents: ({ url }) =>
          url.searchParams.get('limit') === '100' && (listed += 1) === 2
            ? jsonResponse(500, { error: 'internal_error', message: 'Database unavailable.' })
            : jsonResponse(200, page(Array.from({ length: 100 }, (_, i) => incidentFixture({ id: `inc-${i}` })), { total: 150, limit: 100 })),
      }),
    )
    renderReports()

    const download = screen.getByRole('button', { name: 'Download CSV' })
    await waitFor(() => expect(download).toBeEnabled())
    await userEvent.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not export: Database unavailable.')
    expect(click).not.toHaveBeenCalled()
    click.mockRestore()
  })
})
