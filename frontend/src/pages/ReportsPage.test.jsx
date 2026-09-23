import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ReportsPage from './ReportsPage'
import { ADMIN, calls, jsonResponse, page, renderSignedIn, signIn, stubApi } from '../test/helpers'

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

function routes(overrides = {}) {
  return [
    ['GET', '/api/incidents/reports/summary', overrides.summary ?? (() => jsonResponse(200, SUMMARY))],
    ['GET', '/api/incidents/reports/sla', overrides.sla ?? (() => jsonResponse(200, SLA))],
    ['GET', '/api/incidents/reports/volume', overrides.volume ?? (() => jsonResponse(200, VOLUME))],
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
      }),
    )
    renderReports()

    expect(await screen.findAllByRole('heading', { name: 'No incidents in this range' })).toHaveLength(3)
  })
})
