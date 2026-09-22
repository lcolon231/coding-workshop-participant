import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import RegisterPage from './RegisterPage'
import { jsonResponse, renderPage } from '../test/helpers'

const ACCEPTED = 'If this address can be registered, the account is ready. Sign in to continue.'

function renderRegister() {
  return renderPage(<RegisterPage />, { path: '/register' })
}

async function fillValidForm() {
  await userEvent.type(screen.getByLabelText('Full name'), 'Ines Caetano')
  await userEvent.type(screen.getByLabelText('Work email'), 'Ines.Caetano@acme.inc')
  await userEvent.type(screen.getByLabelText('Password'), 'correct horse battery')
  await userEvent.type(screen.getByLabelText('Occupation'), 'Financial Analyst')
  await userEvent.type(screen.getByLabelText('Date of birth'), '1995-01-30')
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('RegisterPage', () => {
  it('labels every input, with helper text, and links to sign-in', () => {
    renderRegister()
    expect(screen.getByRole('heading', { level: 1, name: 'Create your account' })).toBeInTheDocument()
    for (const label of ['Full name', 'Work email', 'Password', 'Occupation', 'Date of birth']) {
      expect(screen.getByLabelText(label)).toBeInTheDocument()
    }
    expect(screen.getByLabelText('Password')).toHaveAccessibleDescription('At least 12 characters.')
    expect(screen.getByLabelText('Date of birth')).toHaveAttribute('max')
    expect(screen.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/login')
  })

  it('checks the domain and password length before calling the API', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    renderRegister()

    await userEvent.type(screen.getByLabelText('Work email'), 'jane@acme.inc.evil.com')
    await userEvent.type(screen.getByLabelText('Password'), 'short')
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(screen.getByText('Enter your full name.')).toBeInTheDocument()
    expect(screen.getByText('Use your @acme.inc address.')).toBeInTheDocument()
    expect(screen.getByText('Use at least 12 characters.')).toBeInTheDocument()
    expect(screen.getByText('Enter your occupation.')).toBeInTheDocument()
    expect(screen.getByText('Enter your date of birth.')).toBeInTheDocument()
    expect(screen.getByLabelText('Full name')).toHaveFocus()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('clears a field error as soon as the field changes', async () => {
    renderRegister()
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(screen.getByText('Enter your full name.')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('Full name'), 'I')
    expect(screen.queryByText('Enter your full name.')).not.toBeInTheDocument()
  })

  it('maps details[] onto the fields on a 400', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(400, {
          error: 'validation_error',
          message: 'Request validation failed.',
          details: [
            { field: 'date_of_birth', message: 'Value error, date_of_birth cannot be in the future' },
            { field: 'occupation', message: 'String should have at most 100 characters' },
          ],
        }),
      ),
    )
    renderRegister()
    await fillValidForm()
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('Date_of_birth cannot be in the future.')).toBeInTheDocument()
    expect(screen.getByText('String should have at most 100 characters.')).toBeInTheDocument()
    expect(screen.getByLabelText('Occupation')).toHaveFocus()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('surfaces a detail for an unknown field at form level', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(400, {
          error: 'validation_error',
          message: 'Request validation failed.',
          details: [{ field: 'role', message: 'Extra inputs are not permitted' }],
        }),
      ),
    )
    renderRegister()
    await fillValidForm()
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'role: Extra inputs are not permitted.',
    )
  })

  it('sends a normalised body and hands the notice to the sign-in screen', async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(202, { message: ACCEPTED }))
    vi.stubGlobal('fetch', fetch)
    renderRegister()
    await fillValidForm()
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByText('Login stub')).toBeInTheDocument()
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('/api/auth/register')
    expect(JSON.parse(init.body)).toEqual({
      full_name: 'Ines Caetano',
      email: 'ines.caetano@acme.inc',
      password: 'correct horse battery',
      occupation: 'Financial Analyst',
      date_of_birth: '1995-01-30',
    })
  })

  it('reports a network failure without losing the form', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    renderRegister()
    await fillValidForm()
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/could not reach the server/i)
    expect(screen.getByLabelText('Full name')).toHaveValue('Ines Caetano')
    expect(screen.getByRole('button', { name: 'Create account' })).toBeEnabled()
  })
})
