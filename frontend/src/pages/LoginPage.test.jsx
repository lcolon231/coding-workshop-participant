import { afterEach, describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import LoginPage from './LoginPage'
import { readSession } from '../services/session'
import { jsonResponse, renderPage } from '../test/helpers'

const TOKENS = { access_token: 'a', refresh_token: 'r', token_type: 'bearer', expires_in: 1800 }

function renderLogin(initialEntries) {
  return renderPage(<LoginPage />, { path: '/login', initialEntries })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LoginPage', () => {
  it('labels every input and offers registration', () => {
    renderLogin()
    expect(screen.getByRole('heading', { level: 1, name: 'Sign in' })).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Create an account' })).toHaveAttribute(
      'href',
      '/register',
    )
  })

  it('validates required fields before calling the API', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    renderLogin()

    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(screen.getByText('Enter your email address.')).toBeInTheDocument()
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
    expect(screen.getByLabelText('Email')).toHaveFocus()
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('shows the API message on bad credentials', async () => {
    const message = 'Invalid email or password, or the account is temporarily locked.'
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(401, { error: 'unauthenticated', message })),
    )
    renderLogin()

    await userEvent.type(screen.getByLabelText('Email'), 'jane@acme.inc')
    await userEvent.type(screen.getByLabelText('Password'), 'not the password')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(readSession()).toBeNull()
  })

  it('maps details[] onto the fields on a 400', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(400, {
          error: 'validation_error',
          message: 'Request validation failed.',
          details: [{ field: 'email', message: 'value is not a valid email address' }],
        }),
      ),
    )
    renderLogin()

    await userEvent.type(screen.getByLabelText('Email'), 'jane')
    await userEvent.type(screen.getByLabelText('Password'), 'whatever')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    const email = screen.getByLabelText('Email')
    expect(await screen.findByText('Value is not a valid email address.')).toBeInTheDocument()
    expect(email).toHaveAttribute('aria-invalid', 'true')
    expect(email).toHaveFocus()
    // Inline errors are enough: the generic envelope message is not repeated.
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('stores the session and goes home on success', async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, TOKENS))
    vi.stubGlobal('fetch', fetch)
    renderLogin()

    await userEvent.type(screen.getByLabelText('Email'), '  Jane@acme.inc ')
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse battery')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Home stub')).toBeInTheDocument()
    expect(readSession()).toMatchObject({ accessToken: 'a', refreshToken: 'r' })
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe('/api/auth/login')
    expect(JSON.parse(init.body)).toEqual({ email: 'Jane@acme.inc', password: 'correct horse battery' })
  })

  it('returns to where the user was going', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, TOKENS)))
    renderLogin([{ pathname: '/login', state: { from: '/register' } }])

    await userEvent.type(screen.getByLabelText('Email'), 'jane@acme.inc')
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse battery')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Register stub')).toBeInTheDocument()
  })

  it('shows the notice carried over from registration', () => {
    renderLogin([{ pathname: '/login', state: { notice: 'Sign in to continue.' } }])
    expect(screen.getByText('Sign in to continue.')).toBeInTheDocument()
  })

  it('disables the button while the request is in flight', async () => {
    let resolve
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise((r) => (resolve = r))))
    renderLogin()

    await userEvent.type(screen.getByLabelText('Email'), 'jane@acme.inc')
    await userEvent.type(screen.getByLabelText('Password'), 'correct horse battery')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(screen.getByRole('button', { name: 'Signing in…' })).toBeDisabled()
    resolve(jsonResponse(200, TOKENS))
    await waitFor(() => expect(screen.getByText('Home stub')).toBeInTheDocument())
  })

  it('reveals the password on request', async () => {
    renderLogin()
    const password = screen.getByLabelText('Password')
    expect(password).toHaveAttribute('type', 'password')
    await userEvent.click(screen.getByRole('button', { name: 'Show password' }))
    expect(password).toHaveAttribute('type', 'text')
    expect(screen.getByRole('button', { name: 'Hide password' })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
  })
})
