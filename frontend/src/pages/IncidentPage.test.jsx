import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import IncidentPage from './IncidentPage'
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

const NOTE = {
  id: 'n-1',
  incident_id: 'inc-1',
  author_id: ENGINEER.id,
  author: ENGINEER,
  body: 'Condensate pump ordered.',
  visibility: 'internal',
  created_at: '2026-09-22T10:00:00Z',
}
const HISTORY = [
  { id: 'h-1', from_status: null, to_status: 'Open', actor_id: EMPLOYEE.id, actor: EMPLOYEE, assignee_id: null, assignee: null, note: null, created_at: '2026-09-22T09:12:00Z' },
  { id: 'h-2', from_status: 'Open', to_status: 'Open', actor_id: ADMIN.id, actor: ADMIN, assignee_id: ENGINEER.id, assignee: ENGINEER, note: null, created_at: '2026-09-22T09:30:00Z' },
  { id: 'h-3', from_status: 'Open', to_status: 'In Progress', actor_id: ENGINEER.id, actor: ENGINEER, assignee_id: null, assignee: null, note: null, created_at: '2026-09-22T09:40:00Z' },
]

/** The detail endpoints for one incident, with the incident itself overridable per call. */
function routes(incident, extra = []) {
  const current = typeof incident === 'function' ? incident : () => incident
  return [
    ['GET', '/api/incidents/inc-1', () => jsonResponse(200, current())],
    ['GET', '/api/incidents/inc-1/notes', () => jsonResponse(200, page([NOTE]))],
    ['GET', '/api/incidents/inc-1/history', () => jsonResponse(200, page(HISTORY))],
    ['GET', '/api/incidents/inc-1/escalations', () => jsonResponse(200, page([]))],
    ['GET', '/api/facilities/buildings/b-1', () => jsonResponse(200, { id: 'b-1', code: 'HQ', name: 'Headquarters', address: null, is_active: true })],
    ['GET', '/api/facilities/floors/f-3', () => jsonResponse(200, { id: 'f-3', building_id: 'b-1', level: 3, name: null })],
    ['GET', '/api/auth/users', () => jsonResponse(200, page([ENGINEER]))],
    ...extra,
  ]
}

function renderDetail(user = EMPLOYEE) {
  signIn()
  return renderSignedIn(<IncidentPage />, { path: '/incidents/:incidentId', initialEntries: ['/incidents/inc-1'], user })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('IncidentPage', () => {
  it('shows the incident, its notes, history and location', async () => {
    stubApi(routes(incidentFixture({ status: 'In Progress', assignee_id: ENGINEER.id, assignee: ENGINEER })))
    renderDetail(ENGINEER)

    expect(await screen.findByRole('heading', { level: 1, name: 'Aircon dripping on desk 3-14' })).toBeInTheDocument()
    expect(screen.getByText('Condensate pump ordered.')).toBeInTheDocument()
    expect(screen.getByText('Internal')).toBeInTheDocument()
    const history = within(screen.getByRole('region', { name: 'History' }))
    expect(history.getAllByRole('listitem').map((item) => item.textContent.replace(/^.*?(?=Reported|Assigned|In Progress)/, ''))).toEqual([
      `Reported by ${EMPLOYEE.full_name}`,
      `Assigned to ${ENGINEER.full_name} by ${ADMIN.full_name}`,
      `In Progress from Open, by ${ENGINEER.full_name}`,
    ])
    expect(await screen.findByText('Headquarters, level 3')).toBeInTheDocument()
    // Where it stands against its target: the chip in the header, the deadline in the details.
    expect(screen.getByText(/^Due in /)).toBeInTheDocument()
    expect(screen.getByText('Target').closest('div')).toHaveTextContent('Sep 25, 2026')
  })

  it('renders exactly the transitions the API allows and prompts for what they require', async () => {
    let incident = incidentFixture({
      status: 'In Progress',
      assignee_id: ENGINEER.id,
      assignee: ENGINEER,
      allowed_transitions: [
        { to: 'Blocked', label: 'Block on an external dependency', requires: ['blocked_reason'] },
        { to: 'Resolved', label: 'Resolve', requires: ['resolution_note'] },
      ],
    })
    const fetch = stubApi(
      routes(
        () => incident,
        [
          ['POST', '/api/incidents/inc-1/transition', ({ body }) => {
            incident = { ...incident, status: body.target_status, allowed_transitions: [] }
            return jsonResponse(200, incident)
          }],
        ],
      ),
    )
    renderDetail(ENGINEER)

    const actions = within(await screen.findByRole('region', { name: 'Actions' }))
    expect(actions.getAllByRole('button')).toHaveLength(2)
    await userEvent.click(actions.getByRole('button', { name: 'Resolve' }))

    const dialog = within(screen.getByRole('dialog'))
    await userEvent.click(dialog.getByRole('button', { name: 'Resolve' }))
    expect(dialog.getByText('This is required to continue.')).toBeInTheDocument()
    expect(calls(fetch).some((c) => c.startsWith('POST'))).toBe(false)

    await userEvent.type(dialog.getByLabelText('Resolution note'), 'Replaced the pump.')
    await userEvent.click(dialog.getByRole('button', { name: 'Resolve' }))

    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(post[1].body)).toEqual({ target_status: 'Resolved', resolution_note: 'Replaced the pump.' })
    expect(await screen.findByText('Now Resolved.')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Actions' })).not.toBeInTheDocument()
  })

  it('lets the assigned engineer start work without naming an assignee', async () => {
    const fetch = stubApi(
      routes(
        incidentFixture({
          assignee_id: ENGINEER.id,
          assignee: ENGINEER,
          allowed_transitions: [{ to: 'In Progress', label: 'Acknowledge and start work', requires: [] }],
        }),
        [['POST', '/api/incidents/inc-1/transition', ({ body }) => jsonResponse(200, incidentFixture({ status: body.target_status }))]],
      ),
    )
    renderDetail(ENGINEER)

    await userEvent.click(await screen.findByRole('button', { name: 'Acknowledge and start work' }))
    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.queryByText(/assigned to you/)).not.toBeInTheDocument()
    expect(dialog.queryByLabelText('Engineer')).not.toBeInTheDocument()
    await userEvent.click(dialog.getByRole('button', { name: 'Acknowledge and start work' }))

    await waitFor(() => {
      const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(JSON.parse(post[1].body)).toEqual({ target_status: 'In Progress' })
    })
  })

  it('never offers an engineer an assignee field, even if the API asked for one', async () => {
    const fetch = stubApi(
      routes(
        incidentFixture({
          allowed_transitions: [{ to: 'In Progress', label: 'Acknowledge and start work', requires: ['assignee_id'] }],
        }),
        [['POST', '/api/incidents/inc-1/transition', ({ body }) => jsonResponse(200, incidentFixture({ status: body.target_status }))]],
      ),
    )
    renderDetail(ENGINEER)

    await userEvent.click(await screen.findByRole('button', { name: 'Acknowledge and start work' }))
    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.queryByLabelText('Engineer')).not.toBeInTheDocument()
    await userEvent.click(dialog.getByRole('button', { name: 'Acknowledge and start work' }))

    await waitFor(() => {
      const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(JSON.parse(post[1].body)).toEqual({ target_status: 'In Progress' })
    })
  })

  it('shows the transition error from the API inside the dialog', async () => {
    stubApi(
      routes(incidentFixture({ allowed_transitions: [{ to: 'Closed', label: 'Close without work', requires: ['resolution_note'] }] }), [
        ['POST', '/api/incidents/inc-1/transition', () => jsonResponse(409, { error: 'conflict', message: 'Someone else moved it first.' })],
      ]),
    )
    renderDetail(ADMIN)

    await userEvent.click(await screen.findByRole('button', { name: 'Close without work' }))
    const dialog = within(screen.getByRole('dialog'))
    await userEvent.type(dialog.getByLabelText('Resolution note'), 'Duplicate of another report.')
    await userEvent.click(dialog.getByRole('button', { name: 'Close without work' }))

    expect(await dialog.findByRole('alert')).toHaveTextContent('Someone else moved it first.')
  })

  it('hides the internal-note toggle from employees and adds a note', async () => {
    const fetch = stubApi(
      routes(incidentFixture(), [['POST', '/api/incidents/inc-1/notes', ({ body }) => jsonResponse(201, { ...NOTE, id: 'n-2', ...body, author: EMPLOYEE })]]),
    )
    renderDetail(EMPLOYEE)

    await screen.findByRole('heading', { level: 1 })
    expect(screen.queryByRole('group', { name: 'Who can read this note' })).not.toBeInTheDocument()
    await userEvent.type(screen.getByLabelText('Add a note'), 'Still dripping this afternoon.')
    await userEvent.click(screen.getByRole('button', { name: 'Add note' }))

    await waitFor(() => {
      const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(JSON.parse(post[1].body)).toEqual({ body: 'Still dripping this afternoon.', visibility: 'public' })
    })
    expect(await screen.findByText('Note added.')).toBeInTheDocument()
  })

  it('lets an admin triage the assignee and priority through PUT', async () => {
    const fetch = stubApi(
      routes(incidentFixture(), [['PUT', '/api/incidents/inc-1', ({ body }) => jsonResponse(200, incidentFixture(body))]]),
    )
    renderDetail(ADMIN)

    const triage = within(await screen.findByRole('form', { name: 'Triage' }))
    await userEvent.selectOptions(await triage.findByLabelText('Assignee'), ENGINEER.id)
    await userEvent.selectOptions(triage.getByLabelText('Priority'), 'High')
    await userEvent.click(triage.getByRole('button', { name: 'Save triage' }))

    await waitFor(() => {
      const put = fetch.mock.calls.find(([, init]) => init?.method === 'PUT')
      expect(JSON.parse(put[1].body)).toEqual({ assignee_id: ENGINEER.id, priority: 'High' })
    })
  })

  it('offers escalation to the reporter and sends the reason', async () => {
    const fetch = stubApi(
      routes(incidentFixture(), [
        ['POST', '/api/incidents/inc-1/escalations', ({ body }) =>
          jsonResponse(201, { id: 'e-1', incident_id: 'inc-1', requested_by: EMPLOYEE, reason: body.reason, status: 'Pending', decided_by: null, decided_at: null, decision_note: null, created_at: '2026-09-22T11:00:00Z' })],
      ]),
    )
    renderDetail(EMPLOYEE)

    await userEvent.click(await screen.findByRole('button', { name: 'Request escalation' }))
    const dialog = within(screen.getByRole('dialog'))
    await userEvent.type(dialog.getByLabelText('Reason'), 'The whole row cannot work.')
    await userEvent.click(dialog.getByRole('button', { name: 'Send request' }))

    await waitFor(() => {
      const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
      expect(JSON.parse(post[1].body)).toEqual({ reason: 'The whole row cannot work.' })
    })
  })

  it('says when an incident cannot be found', async () => {
    stubApi([['GET', '/api/incidents/inc-1', () => jsonResponse(404, { error: 'not_found', message: 'Incident not found.' })]])
    renderDetail()
    expect(await screen.findByRole('heading', { name: 'Incident not found' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to incidents' })).toHaveAttribute('href', '/')
  })
})
