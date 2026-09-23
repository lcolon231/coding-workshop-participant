import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import IncidentsPage from './IncidentsPage'
import { mockViewport } from '../test/setup'
import {
  ADMIN,
  EMPLOYEE,
  ENGINEER,
  calls,
  incidentFixture,
  jsonResponse,
  page,
  renderSignedIn,
  signIn,
  stubApi,
} from '../test/helpers'

const TWO = [
  incidentFixture(),
  incidentFixture({
    id: 'inc-2',
    title: 'Lift stuck between floors',
    status: 'In Progress',
    priority: 'High',
    assignee_id: ENGINEER.id,
    assignee: ENGINEER,
  }),
]

function renderList({ user = EMPLOYEE, initialEntries } = {}) {
  signIn()
  return renderSignedIn(<IncidentsPage />, { path: '/', initialEntries, user })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('IncidentsPage', () => {
  it('lists incidents with links to each one', async () => {
    const fetch = stubApi([['GET', '/api/incidents', () => jsonResponse(200, page(TWO))]])
    renderList()

    expect(await screen.findByRole('link', { name: 'Aircon dripping on desk 3-14' })).toHaveAttribute(
      'href',
      '/incidents/inc-1',
    )
    expect(screen.getByText('Showing 1 to 2 of 2')).toBeInTheDocument()
    const table = screen.getByRole('table')
    expect(within(table).getByText('Hank Vance')).toBeInTheDocument()
    expect(calls(fetch)[0]).toBe('GET /api/incidents?sort=created_at&order=desc&limit=25&offset=0')
    // The admin overview and the export are not for an employee.
    expect(screen.queryByRole('region', { name: 'Overview' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Download CSV' })).not.toBeInTheDocument()
  })

  it('stacks the rows on a phone', async () => {
    mockViewport({ matches: false })
    stubApi([['GET', '/api/incidents', () => jsonResponse(200, page(TWO))]])
    renderList()

    expect(await screen.findByRole('link', { name: 'Lift stuck between floors' })).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByText(/Assigned to Hank Vance/)).toBeInTheDocument()
  })

  it('offers to report the first incident when there are none', async () => {
    stubApi([['GET', '/api/incidents', () => jsonResponse(200, page([]))]])
    renderList()

    expect(await screen.findByRole('heading', { name: 'No incidents yet' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Report an incident' })).toHaveAttribute('href', '/incidents/new')
  })

  it('puts filters in the URL and the request', async () => {
    const fetch = stubApi([['GET', '/api/incidents', () => jsonResponse(200, page(TWO))]])
    renderList()
    await screen.findByText('Showing 1 to 2 of 2')

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'Blocked')

    await waitFor(() =>
      expect(calls(fetch).at(-1)).toBe(
        'GET /api/incidents?status=Blocked&sort=created_at&order=desc&limit=25&offset=0',
      ),
    )
  })

  it('debounces the search box into the request', async () => {
    const fetch = stubApi([['GET', '/api/incidents', () => jsonResponse(200, page(TWO))]])
    renderList()
    await screen.findByText('Showing 1 to 2 of 2')

    await userEvent.type(screen.getByLabelText('Search incidents'), 'lift')

    await waitFor(() => expect(calls(fetch).at(-1)).toContain('search=lift'))
    expect(calls(fetch)).toHaveLength(2)
  })

  it('explains an empty filtered result and can clear the filters', async () => {
    stubApi([
      ['GET', '/api/incidents', ({ url }) => jsonResponse(200, page(url.searchParams.get('status') ? [] : TWO))],
    ])
    renderList({ initialEntries: ['/?status=Closed'] })

    expect(await screen.findByRole('heading', { name: 'No incidents match' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(await screen.findByText('Showing 1 to 2 of 2')).toBeInTheDocument()
  })

  it('shows the API message on failure and retries', async () => {
    let attempts = 0
    stubApi([
      [
        'GET',
        '/api/incidents',
        () =>
          (attempts += 1) === 1
            ? jsonResponse(500, { error: 'internal_error', message: 'Database unavailable.' })
            : jsonResponse(200, page(TWO)),
      ],
    ])
    renderList()

    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable.')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Showing 1 to 2 of 2')).toBeInTheDocument()
  })

  it('gives admins the overview and a CSV of the filtered list, and nobody else', async () => {
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
    const fetch = stubApi([
      ['GET', '/api/incidents/reports/buildings', () => jsonResponse(200, { rows: [{ building_id: 'b-1', building: 'HQ', count: 2, open_count: 1, critical_count: 0 }] })],
      ['GET', '/api/incidents/reports/engineers', () => jsonResponse(200, { rows: [] })],
      ['GET', '/api/facilities/buildings', () => jsonResponse(200, page([{ id: 'b-1', name: 'HQ' }]))],
      [
        'GET',
        '/api/incidents',
        ({ url }) => {
          const offset = Number(url.searchParams.get('offset'))
          if (url.searchParams.get('limit') !== '100') return jsonResponse(200, page(TWO, { total: 101 }))
          const items = offset === 0 ? Array.from({ length: 100 }, (_, i) => incidentFixture({ id: `inc-${i}` })) : [TWO[1]]
          return jsonResponse(200, page(items, { total: 101, limit: 100, offset }))
        },
      ],
    ])
    renderList({ user: ADMIN, initialEntries: ['/?status=Blocked'] })

    expect(await screen.findByRole('region', { name: 'Overview' })).toBeInTheDocument()
    expect(await screen.findByRole('img', { name: /Incidents per building/ })).toBeInTheDocument()
    const download = screen.getByRole('button', { name: 'Download CSV' })
    await waitFor(() => expect(download).toBeEnabled())
    await userEvent.click(download)
    expect(await screen.findByRole('status')).toHaveTextContent('Exported 101 incidents.')
    expect(calls(fetch)).toContain('GET /api/incidents?status=Blocked&sort=created_at&order=asc&limit=100&offset=100')
    expect(click).toHaveBeenCalledTimes(1)
    const text = await saved[0].text()
    expect(text.split('\r\n')[0]).toBe('id,title,status,priority,building,reporter,assignee,reported_at,acknowledged_at,resolved_at,closed_at')
    expect(text).toContain('inc-2,Lift stuck between floors,In Progress,High,HQ,Eve Employee,Hank Vance,2026-09-22T09:12:00Z,,,')
    click.mockRestore()
  })

  it('reports an export that failed instead of saving a partial file', async () => {
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    stubApi([
      ['GET', '/api/incidents/reports/buildings', () => jsonResponse(200, { rows: [] })],
      ['GET', '/api/incidents/reports/engineers', () => jsonResponse(200, { rows: [] })],
      ['GET', '/api/facilities/buildings', () => jsonResponse(500, { error: 'internal_error', message: 'Database unavailable.' })],
      ['GET', '/api/incidents', () => jsonResponse(200, page(TWO))],
    ])
    renderList({ user: ADMIN })

    const download = await screen.findByRole('button', { name: 'Download CSV' })
    await waitFor(() => expect(download).toBeEnabled())
    await userEvent.click(download)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not export: Database unavailable.')
    expect(click).not.toHaveBeenCalled()
    click.mockRestore()
  })

  it('offers "Assigned to me" to engineers only', async () => {
    const fetch = stubApi([['GET', '/api/incidents', () => jsonResponse(200, page(TWO))]])
    const { unmount } = renderList({ user: ENGINEER })
    await screen.findByText('Showing 1 to 2 of 2')

    await userEvent.click(screen.getByRole('checkbox', { name: 'Assigned to me' }))
    await waitFor(() => expect(calls(fetch).at(-1)).toContain(`assignee_id=${ENGINEER.id}`))
    unmount()

    renderList({ user: ADMIN })
    await screen.findByText('Showing 1 to 2 of 2')
    expect(screen.queryByRole('checkbox', { name: 'Assigned to me' })).not.toBeInTheDocument()
  })

  it('shows the confirmation a page arrived with', async () => {
    stubApi([['GET', '/api/incidents', () => jsonResponse(200, page(TWO))]])
    renderList({
      user: ENGINEER,
      initialEntries: [{ pathname: '/', state: { notice: 'Incident created successfully.' } }],
    })
    expect(await screen.findByRole('status')).toHaveTextContent('Incident created successfully.')
  })
})
