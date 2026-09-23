import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import FacilitiesPage from './FacilitiesPage'
import { mockViewport } from '../test/setup'
import { ADMIN, calls, jsonResponse, page, renderSignedIn, signIn, stubApi } from '../test/helpers'

const HQ = { id: 'b-hq', code: 'HQ', name: 'Headquarters', address: '1 Acme Way', is_active: true }
const RVA = { id: 'b-rva', code: 'RVA', name: 'Riverside Annex', address: '40 Quay Street', is_active: true }
const FLOORS = [
  { id: 'f-1', building_id: 'b-hq', level: 1, name: 'Lobby and Reception' },
  { id: 'f-2', building_id: 'b-hq', level: 2, name: 'Engineering' },
]
const SEATS = [
  { id: 's-1', floor_id: 'f-2', code: '2-01', label: null, is_active: true },
  { id: 's-2', floor_id: 'f-2', code: '2-02', label: 'Window desk', is_active: false },
]
const CATEGORIES = [
  { id: 'c-fac', name: 'Facilities', parent_id: null, description: null, is_active: true },
  { id: 'c-hvac', name: 'HVAC', parent_id: 'c-fac', description: 'Heating and cooling', is_active: true },
  { id: 'c-tech', name: 'Workplace Technology', parent_id: null, description: null, is_active: true },
  { id: 'c-net', name: 'Network', parent_id: 'c-tech', description: null, is_active: true },
]
const ENGINEERS = [
  {
    user_id: 'u-eng',
    specialty: 'HVAC',
    max_concurrent_incidents: 5,
    is_available: true,
    user: { id: 'u-eng', full_name: 'Hank Vance', role: 'Engineer' },
    open_assignments: 2,
  },
  {
    user_id: 'u-ivy',
    specialty: 'Workplace Technology',
    max_concurrent_incidents: 3,
    is_available: false,
    user: { id: 'u-ivy', full_name: 'Ivy Tran', role: 'Engineer' },
    open_assignments: 3,
  },
]

function baseRoutes() {
  return [
    ['GET', '/api/facilities/buildings', () => jsonResponse(200, page([HQ, RVA]))],
    ['GET', '/api/facilities/buildings/b-hq/floors', () => jsonResponse(200, page(FLOORS))],
    ['GET', '/api/facilities/buildings/b-rva/floors', () => jsonResponse(200, page([]))],
    ['GET', '/api/facilities/floors/f-2/seats', () => jsonResponse(200, page(SEATS))],
    ['GET', '/api/facilities/categories', () => jsonResponse(200, page(CATEGORIES))],
    ['GET', '/api/facilities/engineers', () => jsonResponse(200, page(ENGINEERS))],
  ]
}

function renderFacilities({ initialEntries } = {}) {
  signIn()
  return renderSignedIn(<FacilitiesPage />, { path: '/facilities', initialEntries, user: ADMIN })
}

function section(name) {
  return screen.getByRole('region', { name })
}

async function openMenu(name) {
  await userEvent.click(await screen.findByRole('button', { name: `Actions for ${name}` }))
  return screen.getByRole('menu')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('FacilitiesPage', () => {
  it('drills from buildings to floors to seats through the URL', async () => {
    const fetch = stubApi(baseRoutes())
    renderFacilities()

    expect(await screen.findByText('HQ · Headquarters')).toBeInTheDocument()
    expect(calls(fetch)[0]).toBe('GET /api/facilities/buildings?limit=100')
    expect(within(section('Floors')).getByText('Choose a building to see its floors.')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /^HQ · Headquarters/ }))
    expect(await screen.findByText('Level 2 · Engineering')).toBeInTheDocument()
    expect(calls(fetch)).toContain('GET /api/facilities/buildings/b-hq/floors?limit=100')

    await userEvent.click(screen.getByRole('button', { name: /^Level 2 · Engineering/ }))
    expect(await screen.findByText('2-02 · Window desk')).toBeInTheDocument()
    expect(calls(fetch)).toContain('GET /api/facilities/floors/f-2/seats?limit=100')
    // The retired seat is marked; the switch adds `include_inactive`.
    expect(within(section('Seats')).getByText('Retired')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('switch', { name: 'Show retired' }))
    await waitFor(() =>
      expect(calls(fetch)).toContain('GET /api/facilities/buildings?limit=100&include_inactive=true'),
    )
    expect(calls(fetch)).toContain('GET /api/facilities/floors/f-2/seats?limit=100&include_inactive=true')
  })

  it('adds a floor to the selected building', async () => {
    const fetch = stubApi([
      ...baseRoutes(),
      ['POST', '/api/facilities/floors', ({ body }) => jsonResponse(201, { id: 'f-new', ...body })],
    ])
    renderFacilities({ initialEntries: ['/facilities?building=b-hq'] })
    await screen.findByText('Level 2 · Engineering')

    await userEvent.click(screen.getByRole('button', { name: 'Add floor' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Add a floor to Headquarters' })).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }))
    expect(within(dialog).getByText('This is required.')).toBeInTheDocument()

    await userEvent.type(within(dialog).getByLabelText('Level'), '-1')
    await userEvent.type(within(dialog).getByLabelText('Name'), 'Car park')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }))

    expect(await screen.findByText('Floor added.')).toBeInTheDocument()
    const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(post[1].body)).toEqual({ building_id: 'b-hq', level: -1, name: 'Car park' })
    await waitFor(() =>
      expect(calls(fetch).filter((call) => call === 'GET /api/facilities/buildings/b-hq/floors?limit=100')).toHaveLength(2),
    )
  })

  it('edits a building without its immutable code and sends only changes', async () => {
    const fetch = stubApi([
      ...baseRoutes(),
      ['PUT', '/api/facilities/buildings/b-hq', ({ body }) => jsonResponse(200, { ...HQ, ...body })],
    ])
    renderFacilities()
    await screen.findByText('HQ · Headquarters')

    const menu = await openMenu('HQ · Headquarters')
    await userEvent.click(within(menu).getByRole('menuitem', { name: 'Edit' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByLabelText('Code')).toBeDisabled()
    await userEvent.clear(within(dialog).getByLabelText('Address'))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Building saved.')).toBeInTheDocument()
    const put = fetch.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(put[1].body)).toEqual({ address: null })
  })

  it('retires from the row menu and shows a delete refusal inline', async () => {
    const fetch = stubApi([
      ...baseRoutes(),
      ['PUT', '/api/facilities/buildings/b-rva', ({ body }) => jsonResponse(200, { ...RVA, ...body })],
      [
        'DELETE',
        '/api/facilities/buildings/b-hq',
        () =>
          jsonResponse(409, {
            error: 'conflict',
            message: 'Building has 3 floors and 12 incidents; deactivate it instead.',
          }),
      ],
    ])
    renderFacilities()
    await screen.findByText('HQ · Headquarters')

    let menu = await openMenu('RVA · Riverside Annex')
    await userEvent.click(within(menu).getByRole('menuitem', { name: 'Retire' }))
    expect(await screen.findByText('Riverside Annex retired.')).toBeInTheDocument()
    const put = fetch.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(put[1].body)).toEqual({ is_active: false })

    menu = await openMenu('HQ · Headquarters')
    await userEvent.click(within(menu).getByRole('menuitem', { name: 'Delete' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Delete Headquarters?' })).toBeInTheDocument()
    await userEvent.click(within(dialog).getByRole('button', { name: 'Delete' }))
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('Building has 3 floors and 12 incidents; deactivate it instead.')
  })

  it('shows categories as a two-level tree and adds a sub-category under its root', async () => {
    const fetch = stubApi([
      ...baseRoutes(),
      ['POST', '/api/facilities/categories', ({ body }) => jsonResponse(201, { id: 'c-new', is_active: true, ...body })],
    ])
    renderFacilities({ initialEntries: ['/facilities?tab=categories'] })

    expect(await screen.findByRole('list', { name: 'Facilities' })).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Facilities' })).getByText('HVAC')).toBeInTheDocument()
    expect(within(screen.getByRole('list', { name: 'Workplace Technology' })).getByText('Network')).toBeInTheDocument()
    expect(calls(fetch)).toContain('GET /api/facilities/categories?limit=100')

    const menu = await openMenu('Facilities')
    await userEvent.click(within(menu).getByRole('menuitem', { name: 'Add sub-category' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByRole('heading', { name: 'Add a sub-category under Facilities' })).toBeInTheDocument()
    await userEvent.type(within(dialog).getByLabelText('Name'), 'Plumbing')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Create' }))

    expect(await screen.findByText('Category added.')).toBeInTheDocument()
    const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(post[1].body)).toEqual({ parent_id: 'c-fac', name: 'Plumbing' })
    // A sub-category has no "Add sub-category" of its own: the tree is two levels.
    const child = await openMenu('HVAC')
    expect(within(child).queryByRole('menuitem', { name: 'Add sub-category' })).not.toBeInTheDocument()
  })

  it('lists engineers with their load and edits a profile', async () => {
    const fetch = stubApi([
      ...baseRoutes(),
      ['PUT', '/api/facilities/engineers/u-ivy', ({ body }) => jsonResponse(200, { ...ENGINEERS[1], ...body })],
    ])
    renderFacilities({ initialEntries: ['/facilities?tab=engineers'] })

    expect(await screen.findByText('Ivy Tran')).toBeInTheDocument()
    expect(calls(fetch)).toContain('GET /api/facilities/engineers?limit=100&sort=full_name&order=asc')
    expect(screen.queryByRole('switch', { name: 'Show retired' })).not.toBeInTheDocument()
    const row = screen.getByText('Ivy Tran').closest('tr')
    expect(within(row).getByText('3 of 3')).toBeInTheDocument()
    expect(within(row).getByText('Unavailable')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Availability'), 'yes')
    await waitFor(() =>
      expect(calls(fetch)).toContain('GET /api/facilities/engineers?limit=100&sort=full_name&order=asc&is_available=true'),
    )

    await userEvent.click(within(screen.getByText('Ivy Tran').closest('tr')).getByRole('button', { name: 'Edit' }))
    const dialog = screen.getByRole('dialog')
    await userEvent.clear(within(dialog).getByLabelText('Maximum open assignments'))
    await userEvent.type(within(dialog).getByLabelText('Maximum open assignments'), '6')
    await userEvent.click(within(dialog).getByLabelText('Available for new assignments'))
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Ivy Tran saved.')).toBeInTheDocument()
    const put = fetch.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(put[1].body)).toEqual({ max_concurrent_incidents: 6, is_available: true })
  })

  it('shows one column at a time on a phone, with a way back', async () => {
    mockViewport({ matches: false })
    stubApi(baseRoutes())
    renderFacilities({ initialEntries: ['/facilities?building=b-hq'] })

    expect(await screen.findByText('Level 2 · Engineering')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Buildings' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Buildings' }))
    expect(await screen.findByText('HQ · Headquarters')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Floors' })).not.toBeInTheDocument()
  })

  it('shows a failed list with a retry', async () => {
    let attempts = 0
    stubApi([
      ...baseRoutes().filter(([, path]) => path !== '/api/facilities/buildings'),
      [
        'GET',
        '/api/facilities/buildings',
        () =>
          (attempts += 1) === 1
            ? jsonResponse(500, { error: 'internal_error', message: 'Database unavailable.' })
            : jsonResponse(200, page([HQ])),
      ],
    ])
    renderFacilities()

    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable.')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('HQ · Headquarters')).toBeInTheDocument()
  })
})
