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
})
