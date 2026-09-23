import { afterEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import UsersPage from './UsersPage'
import { mockViewport } from '../test/setup'
import { ADMIN, calls, jsonResponse, page, renderSignedIn, signIn, stubApi, userFixture } from '../test/helpers'

const ROWS = [
  userFixture({
    id: ADMIN.id,
    email: 'admin@acme.inc',
    full_name: 'Ada Admin',
    role: 'Facility Admin',
    occupation: null,
    date_of_birth: '1984-03-12',
  }),
  userFixture(),
  userFixture({ id: 'u-old', email: 'old@acme.inc', full_name: 'Olive Old', is_active: false }),
]

function renderUsers({ initialEntries } = {}) {
  signIn()
  return renderSignedIn(<UsersPage />, { path: '/users', initialEntries, user: ADMIN })
}

function listRoute(rows = ROWS) {
  return ['GET', '/api/auth/users', () => jsonResponse(200, page(rows))]
}

function dialog() {
  return screen.getByRole('dialog')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('UsersPage', () => {
  it('lists users with the default sort and marks the signed-in admin', async () => {
    const fetch = stubApi([listRoute()])
    renderUsers()

    expect(await screen.findByText('Showing 1 to 3 of 3')).toBeInTheDocument()
    expect(calls(fetch)[0]).toBe('GET /api/auth/users?sort=created_at&order=desc&limit=25&offset=0')
    const table = screen.getByRole('table')
    expect(within(table).getByText('(you)')).toBeInTheDocument()
    expect(within(table).getByText('employee@acme.inc')).toBeInTheDocument()
    expect(within(table).getAllByText('Inactive')).toHaveLength(1)

    const ownRow = within(table).getByText('admin@acme.inc').closest('tr')
    expect(within(ownRow).getByRole('button', { name: 'Deactivate' })).toBeDisabled()
    const otherRow = within(table).getByText('employee@acme.inc').closest('tr')
    expect(within(otherRow).getByRole('button', { name: 'Deactivate' })).toBeEnabled()
    const inactiveRow = within(table).getByText('old@acme.inc').closest('tr')
    expect(within(inactiveRow).getByRole('button', { name: 'Reactivate' })).toBeInTheDocument()
  })

  it('puts the status filter in the URL and the request', async () => {
    const fetch = stubApi([listRoute()])
    renderUsers()
    await screen.findByText('Showing 1 to 3 of 3')

    await userEvent.selectOptions(screen.getByLabelText('Status'), 'inactive')

    await waitFor(() =>
      expect(calls(fetch).at(-1)).toBe(
        'GET /api/auth/users?is_active=false&sort=created_at&order=desc&limit=25&offset=0',
      ),
    )
  })

  it('creates an engineer with a specialty and reloads', async () => {
    const fetch = stubApi([
      listRoute(),
      ['POST', '/api/auth/users', ({ body }) => jsonResponse(201, userFixture({ id: 'u-new', ...body }))],
    ])
    renderUsers()
    await screen.findByText('Showing 1 to 3 of 3')

    await userEvent.click(screen.getByRole('button', { name: 'New user' }))
    const form = dialog()
    await userEvent.type(within(form).getByLabelText('Full name'), 'Sam Lee')
    await userEvent.type(within(form).getByLabelText('Work email'), 'Sam@acme.inc')
    await userEvent.type(within(form).getByLabelText('Temporary password'), 'correct-horse-battery')
    expect(within(form).queryByLabelText('Specialty')).not.toBeInTheDocument()
    await userEvent.selectOptions(within(form).getByLabelText('Role'), 'Engineer')
    await userEvent.type(within(form).getByLabelText('Specialty'), 'HVAC')
    fireEvent.change(within(form).getByLabelText('Date of birth'), { target: { value: '1990-05-05' } })
    await userEvent.click(within(form).getByRole('button', { name: 'Create user' }))

    expect(await screen.findByText('Sam Lee created as Engineer.')).toBeInTheDocument()
    const post = fetch.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(post[1].body)).toEqual({
      email: 'sam@acme.inc',
      password: 'correct-horse-battery',
      full_name: 'Sam Lee',
      role: 'Engineer',
      specialty: 'HVAC',
      date_of_birth: '1990-05-05',
    })
    await waitFor(() => expect(calls(fetch).filter((call) => call.startsWith('GET'))).toHaveLength(2))
  })

  it('validates before sending and shows a conflict in the dialog', async () => {
    stubApi([
      listRoute(),
      [
        'POST',
        '/api/auth/users',
        () => jsonResponse(409, { error: 'conflict', message: 'A user with this email already exists.' }),
      ],
    ])
    renderUsers()
    await screen.findByText('Showing 1 to 3 of 3')

    await userEvent.click(screen.getByRole('button', { name: 'New user' }))
    const form = dialog()
    await userEvent.click(within(form).getByRole('button', { name: 'Create user' }))
    expect(within(form).getByText('Enter their full name.')).toBeInTheDocument()
    expect(within(form).getByLabelText('Full name')).toHaveFocus()

    await userEvent.type(within(form).getByLabelText('Full name'), 'Eve Employee')
    await userEvent.type(within(form).getByLabelText('Work email'), 'employee@acme.inc')
    await userEvent.type(within(form).getByLabelText('Temporary password'), 'correct-horse-battery')
    await userEvent.type(within(form).getByLabelText('Occupation'), 'Analyst')
    fireEvent.change(within(form).getByLabelText('Date of birth'), { target: { value: '1995-01-30' } })
    await userEvent.click(within(form).getByRole('button', { name: 'Create user' }))

    expect(await within(form).findByRole('alert')).toHaveTextContent('A user with this email already exists.')
  })

  it('edits a user and sends only what changed', async () => {
    const fetch = stubApi([
      listRoute(),
      ['PUT', '/api/auth/users/u-emp', ({ body }) => jsonResponse(200, userFixture(body))],
    ])
    renderUsers()
    await screen.findByText('Showing 1 to 3 of 3')

    const row = screen.getByText('employee@acme.inc').closest('tr')
    await userEvent.click(within(row).getByRole('button', { name: 'Edit' }))
    const form = dialog()
    expect(within(form).getByLabelText('Email')).toBeDisabled()
    await userEvent.clear(within(form).getByLabelText('Full name'))
    await userEvent.type(within(form).getByLabelText('Full name'), 'Eve Evans')
    await userEvent.click(within(form).getByRole('button', { name: 'Save changes' }))

    expect(await screen.findByText('Eve Evans saved.')).toBeInTheDocument()
    const put = fetch.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(put[1].body)).toEqual({ full_name: 'Eve Evans' })
  })

  it('locks role and active state when an admin edits themselves', async () => {
    stubApi([listRoute()])
    renderUsers()
    await screen.findByText('Showing 1 to 3 of 3')

    const row = screen.getByText('admin@acme.inc').closest('tr')
    await userEvent.click(within(row).getByRole('button', { name: 'Edit' }))
    const form = dialog()
    expect(within(form).getByLabelText('Role')).toBeDisabled()
    expect(within(form).getByLabelText('Active')).toBeDisabled()
    expect(within(form).getByText('You cannot change your own role.')).toBeInTheDocument()
  })

  it('deactivates after confirmation and shows the API refusal otherwise', async () => {
    let refuse = true
    const fetch = stubApi([
      listRoute(),
      [
        'DELETE',
        '/api/auth/users/u-emp',
        () =>
          refuse
            ? jsonResponse(409, { error: 'conflict', message: 'This engineer has 2 open assignments; reassign them first.' })
            : new Response(null, { status: 204 }),
      ],
    ])
    renderUsers()
    await screen.findByText('Showing 1 to 3 of 3')

    const row = screen.getByText('employee@acme.inc').closest('tr')
    await userEvent.click(within(row).getByRole('button', { name: 'Deactivate' }))
    const confirm = dialog()
    expect(within(confirm).getByRole('heading', { name: 'Deactivate Eve Employee?' })).toBeInTheDocument()
    await userEvent.click(within(confirm).getByRole('button', { name: 'Deactivate' }))
    expect(await within(confirm).findByRole('alert')).toHaveTextContent('reassign them first')

    refuse = false
    await userEvent.click(within(confirm).getByRole('button', { name: 'Deactivate' }))
    expect(await screen.findByText('Eve Employee deactivated.')).toBeInTheDocument()
    expect(calls(fetch)).toContain('DELETE /api/auth/users/u-emp')
  })

  it('reactivates in one click', async () => {
    const fetch = stubApi([
      listRoute(),
      ['PUT', '/api/auth/users/u-old', ({ body }) => jsonResponse(200, userFixture({ id: 'u-old', full_name: 'Olive Old', ...body }))],
    ])
    renderUsers()
    await screen.findByText('Showing 1 to 3 of 3')

    await userEvent.click(screen.getByRole('button', { name: 'Reactivate' }))
    expect(await screen.findByText('Olive Old reactivated.')).toBeInTheDocument()
    const put = fetch.mock.calls.find(([, init]) => init?.method === 'PUT')
    expect(JSON.parse(put[1].body)).toEqual({ is_active: true })
  })

  it('stacks the rows on a phone and explains an empty filter', async () => {
    mockViewport({ matches: false })
    stubApi([['GET', '/api/auth/users', ({ url }) => jsonResponse(200, page(url.searchParams.get('role') ? [] : ROWS))]])
    renderUsers()

    expect(await screen.findByText('Showing 1 to 3 of 3')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByText('Ada Admin (you)')).toBeInTheDocument()

    await userEvent.selectOptions(screen.getByLabelText('Role'), 'Engineer')
    expect(await screen.findByRole('heading', { name: 'No users match' })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Clear filters' }))
    expect(await screen.findByText('Showing 1 to 3 of 3')).toBeInTheDocument()
  })

  it('shows the API message on failure and retries', async () => {
    let attempts = 0
    stubApi([
      [
        'GET',
        '/api/auth/users',
        () =>
          (attempts += 1) === 1
            ? jsonResponse(500, { error: 'internal_error', message: 'Database unavailable.' })
            : jsonResponse(200, page(ROWS)),
      ],
    ])
    renderUsers()

    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable.')
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByText('Showing 1 to 3 of 3')).toBeInTheDocument()
  })
})
