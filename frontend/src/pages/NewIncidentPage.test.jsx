import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import NewIncidentPage from './NewIncidentPage'
import { calls, incidentFixture, jsonResponse, page, renderSignedIn, signIn, stubApi } from '../test/helpers'

const BUILDINGS = [
  { id: 'b-1', code: 'HQ', name: 'Headquarters', address: null, is_active: true },
  { id: 'b-2', code: 'LAB', name: 'Laboratory', address: null, is_active: true },
]
const FLOORS = { 'b-1': [{ id: 'f-3', building_id: 'b-1', level: 3, name: null }], 'b-2': [] }
const SEATS = [{ id: 's-1', floor_id: 'f-3', code: '3-14', label: 'Window desk', is_active: true }]
const CATEGORIES = [
  { id: 'c-1', name: 'Climate', parent_id: null, description: null, is_active: true },
  { id: 'c-2', name: 'Air conditioning', parent_id: 'c-1', description: null, is_active: true },
]

function facilities() {
  return [
    ['GET', '/api/facilities/buildings', () => jsonResponse(200, page(BUILDINGS))],
    ['GET', '/api/facilities/categories', () => jsonResponse(200, page(CATEGORIES))],
    ['GET', /^\/api\/facilities\/buildings\/(.+)\/floors$/, ({ url }) => jsonResponse(200, page(FLOORS[url.pathname.split('/')[4]]))],
    ['GET', '/api/facilities/floors/f-3/seats', () => jsonResponse(200, page(SEATS))],
  ]
}

function renderForm() {
  signIn()
  return renderSignedIn(<NewIncidentPage />, { path: '/incidents/new' })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('NewIncidentPage', () => {
  it('validates before calling the API', async () => {
    const fetch = stubApi(facilities())
    renderForm()
    await screen.findByRole('option', { name: 'Choose a building' })

    await userEvent.click(screen.getByRole('button', { name: 'Submit report' }))

    expect(screen.getByText('Give the incident a short title.')).toBeInTheDocument()
    expect(screen.getByText('Describe what is wrong and where.')).toBeInTheDocument()
    expect(screen.getByText('Choose the building.')).toBeInTheDocument()
    expect(screen.getByLabelText('Title')).toHaveFocus()
    expect(calls(fetch).some((c) => c.startsWith('POST'))).toBe(false)
  })

  it('cascades building to floor to seat and resets downstream choices', async () => {
    stubApi(facilities())
    renderForm()

    const building = screen.getByLabelText('Building')
    const floor = screen.getByLabelText('Floor')
    const seat = screen.getByLabelText('Seat')
    expect(floor).toBeDisabled()
    await screen.findByRole('option', { name: 'HQ, Headquarters' })

    await userEvent.selectOptions(building, 'b-1')
    await userEvent.selectOptions(floor, await screen.findByRole('option', { name: 'Level 3' }))
    await userEvent.selectOptions(seat, await screen.findByRole('option', { name: '3-14, Window desk' }))
    expect(seat).toHaveValue('s-1')

    await userEvent.selectOptions(building, 'b-2')
    expect(floor).toHaveValue('')
    expect(seat).toHaveValue('')
    expect(seat).toBeDisabled()
  })

  it('submits the report and opens the new incident', async () => {
    const fetch = stubApi([
      ...facilities(),
      ['POST', '/api/incidents', ({ body }) => jsonResponse(201, incidentFixture({ id: 'inc-9', ...body }))],
    ])
    renderForm()
    await screen.findByRole('option', { name: 'HQ, Headquarters' })

    await userEvent.type(screen.getByLabelText('Title'), 'Aircon dripping')
    await userEvent.type(screen.getByLabelText('Description'), 'Water on desk 3-14 since 9am.')
    await userEvent.selectOptions(screen.getByLabelText('Priority'), 'High')
    await userEvent.selectOptions(screen.getByLabelText('Category'), 'c-2')
    await userEvent.selectOptions(screen.getByLabelText('Building'), 'b-1')
    await userEvent.selectOptions(screen.getByLabelText('Floor'), await screen.findByRole('option', { name: 'Level 3' }))
    await userEvent.click(screen.getByRole('button', { name: 'Submit report' }))

    expect(await screen.findByText('Detail stub')).toBeInTheDocument()
    const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(post[1].body)).toEqual({
      title: 'Aircon dripping',
      description: 'Water on desk 3-14 since 9am.',
      priority: 'High',
      category_id: 'c-2',
      building_id: 'b-1',
      floor_id: 'f-3',
      seat_id: null,
    })
  })

  it('maps details[] onto the fields on a 400', async () => {
    stubApi([
      ...facilities(),
      ['POST', '/api/incidents', () =>
        jsonResponse(400, {
          error: 'validation_error',
          message: 'Request validation failed.',
          details: [{ field: 'building_id', message: 'Building does not exist.' }],
        })],
    ])
    renderForm()
    await screen.findByRole('option', { name: 'HQ, Headquarters' })

    await userEvent.type(screen.getByLabelText('Title'), 'Lift stuck')
    await userEvent.type(screen.getByLabelText('Description'), 'Between 2 and 3.')
    await userEvent.selectOptions(screen.getByLabelText('Building'), 'b-2')
    await userEvent.click(screen.getByRole('button', { name: 'Submit report' }))

    expect(await screen.findByText('Building does not exist.')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByLabelText('Building')).toHaveFocus())
  })

  it('says when the buildings cannot be loaded and can retry', async () => {
    let attempts = 0
    stubApi([
      ...facilities().slice(1),
      ['GET', '/api/facilities/buildings', () =>
        (attempts += 1) === 1
          ? jsonResponse(503, { error: 'internal_error', message: 'Waking the database.' })
          : jsonResponse(200, page(BUILDINGS))],
    ])
    renderForm()

    expect(await screen.findByRole('alert')).toHaveTextContent('Buildings could not be loaded.')
    expect(screen.getByLabelText('Building')).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('option', { name: 'HQ, Headquarters' })).toBeInTheDocument()
    expect(screen.getByLabelText('Building')).toBeEnabled()
  })
})
