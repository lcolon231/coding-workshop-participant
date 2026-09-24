import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import EscalationsPage from './EscalationsPage'
import { ADMIN, EMPLOYEE, calls, jsonResponse, page, renderSignedIn, signIn, stubApi } from '../test/helpers'

const QUEUE = '/api/incidents/escalations'

function escalation(overrides = {}) {
  return {
    id: 'e-1',
    incident_id: 'inc-1',
    incident_title: 'Aircon dripping on desk 3-14',
    incident_status: 'In Progress',
    incident_priority: 'Low',
    requested_by: EMPLOYEE,
    reason: 'The whole row cannot work.',
    status: 'Pending',
    decided_by: null,
    decided_at: null,
    decision_note: null,
    created_at: '2026-09-22T11:00:00Z',
    ...overrides,
  }
}

function renderQueue(search = '') {
  signIn()
  return renderSignedIn(<EscalationsPage />, { path: '/escalations', initialEntries: [`/escalations${search}`], user: ADMIN })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('EscalationsPage', () => {
  it('lists pending requests with the incident they are about', async () => {
    const fetch = stubApi([['GET', QUEUE, () => jsonResponse(200, page([escalation()]))]])
    renderQueue()

    expect(await screen.findByRole('link', { name: 'Aircon dripping on desk 3-14' })).toHaveAttribute('href', '/incidents/inc-1')
    expect(screen.getByText('The whole row cannot work.')).toBeInTheDocument()
    expect(screen.getByText('In Progress')).toBeInTheDocument()
    expect(screen.getByText('Low')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeInTheDocument()
    expect(calls(fetch)[0]).toBe('GET /api/incidents/escalations?limit=50&status=Pending')
  })

  it('approves with a note, tells the admin the new priority and reloads', async () => {
    let items = [escalation()]
    const fetch = stubApi([
      ['GET', QUEUE, () => jsonResponse(200, page(items))],
      ['POST', `${QUEUE}/e-1/decision`, ({ body }) => {
        items = []
        return jsonResponse(200, escalation({ status: body.decision, decision_note: body.decision_note, decided_by: ADMIN, incident_priority: 'Medium' }))
      }],
    ])
    renderQueue()

    await userEvent.click(await screen.findByRole('button', { name: 'Approve' }))
    const dialog = within(screen.getByRole('dialog', { name: 'Approve escalation' }))
    expect(dialog.getByText(/goes up one priority level/)).toBeInTheDocument()
    await userEvent.type(dialog.getByLabelText('Note'), 'Agreed, the row is out.')
    await userEvent.click(dialog.getByRole('button', { name: 'Approve' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Escalation approved. “Aircon dripping on desk 3-14” is now Medium.')
    const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(post[1].body)).toEqual({ decision: 'Approved', decision_note: 'Agreed, the row is out.' })
    expect(await screen.findByRole('heading', { name: 'No pending escalations' })).toBeInTheDocument()
  })

  it('rejects without a note and keeps the dialog open on a refusal', async () => {
    let attempt = 0
    stubApi([
      ['GET', QUEUE, () => jsonResponse(200, page([escalation()]))],
      ['POST', `${QUEUE}/e-1/decision`, ({ body }) => {
        attempt += 1
        if (attempt === 1) return jsonResponse(409, { error: 'conflict', message: 'This escalation was already approved.' })
        return jsonResponse(200, escalation({ status: body.decision, decided_by: ADMIN }))
      }],
    ])
    renderQueue()

    await userEvent.click(await screen.findByRole('button', { name: 'Reject' }))
    const dialog = within(screen.getByRole('dialog', { name: 'Reject escalation' }))
    await userEvent.click(dialog.getByRole('button', { name: 'Reject' }))
    expect(await dialog.findByText('This escalation was already approved.')).toBeInTheDocument()

    await userEvent.click(dialog.getByRole('button', { name: 'Reject' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Escalation rejected for “Aircon dripping on desk 3-14”.')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('filters by status from the URL and shows decided requests read-only', async () => {
    const fetch = stubApi([
      ['GET', QUEUE, ({ url }) =>
        jsonResponse(200, page(url.searchParams.get('status') === 'Approved'
          ? [escalation({ status: 'Approved', decided_by: ADMIN, decision_note: 'Agreed', incident_priority: 'Medium' })]
          : [])),
      ],
    ])
    renderQueue('?status=Approved')

    expect(await screen.findByText('Approved by Ada Admin: Agreed')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Status')).toHaveValue('Approved')

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'Rejected')
    expect(await screen.findByRole('heading', { name: 'No rejected escalations' })).toBeInTheDocument()
    expect(calls(fetch).at(-1)).toBe('GET /api/incidents/escalations?limit=50&status=Rejected')
  })

  it('offers a retry when the queue fails to load', async () => {
    let attempt = 0
    stubApi([
      ['GET', QUEUE, () => {
        attempt += 1
        return attempt === 1
          ? jsonResponse(500, { error: 'internal_error', message: 'Something broke.' })
          : jsonResponse(200, page([]))
      }],
    ])
    renderQueue()

    expect(await screen.findByText('Something broke.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('heading', { name: 'No pending escalations' })).toBeInTheDocument()
  })
})
