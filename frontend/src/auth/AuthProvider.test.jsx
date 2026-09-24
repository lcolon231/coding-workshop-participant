import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AuthProvider from './AuthProvider'
import { useAuth } from './AuthContext'
import { readSession, saveSession } from '../services/session'
import { EMPLOYEE, jsonResponse, stubApi } from '../test/helpers'

/** Prints the provider's state so a test can read it back. */
function Probe() {
  const { status, user, error, signOut, retry } = useAuth()
  return (
    <div>
      <p data-testid="status">{status}</p>
      {user && <p>Signed in as {user.full_name}</p>}
      {error && <p role="alert">{error}</p>}
      <button onClick={signOut}>Sign out</button>
      <button onClick={retry}>Retry</button>
    </div>
  )
}

function renderProvider() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )
}

const TOKENS = { access_token: 'access', refresh_token: 'refresh', expires_in: 1800 }

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('AuthProvider', () => {
  it('is anonymous without a stored session and never calls the API', () => {
    const fetch = stubApi([])
    renderProvider()

    expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    expect(fetch).not.toHaveBeenCalled()
  })

  it('loads the user from /me when a session is stored, rather than decoding the token', async () => {
    const fetch = stubApi([['GET', '/api/auth/me', () => jsonResponse(200, EMPLOYEE)]])
    saveSession(TOKENS)
    renderProvider()

    expect(screen.getByTestId('status')).toHaveTextContent('loading')
    expect(await screen.findByText('Signed in as Eve Employee')).toBeInTheDocument()
    expect(screen.getByTestId('status')).toHaveTextContent('signed-in')
    const [, init] = fetch.mock.calls[0]
    expect(init.headers['X-Acme-Authorization']).toBe('Bearer access')
  })

  it('clears a session the API rejects, which makes the app anonymous', async () => {
    stubApi([
      ['GET', '/api/auth/me', () => jsonResponse(401, { error: 'unauthorized', message: 'Token expired.' })],
      ['POST', '/api/auth/refresh', () => jsonResponse(401, { error: 'unauthorized', message: 'Refresh revoked.' })],
    ])
    saveSession(TOKENS)
    renderProvider()

    await waitFor(() => expect(screen.getByTestId('status')).toHaveTextContent('anonymous'))
    expect(readSession()).toBeNull()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('reports any other failure and retries from the stored session', async () => {
    let attempts = 0
    stubApi([
      [
        'GET',
        '/api/auth/me',
        () =>
          (attempts += 1) === 1
            ? jsonResponse(500, { error: 'internal_error', message: 'Database unavailable.' })
            : jsonResponse(200, EMPLOYEE),
      ],
    ])
    saveSession(TOKENS)
    renderProvider()

    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable.')
    expect(screen.getByTestId('status')).toHaveTextContent('error')
    // The session is kept: the failure was the server's, not the token's.
    expect(readSession()).not.toBeNull()

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Signed in as Eve Employee')).toBeInTheDocument()
  })

  it('retrying without a session lands on anonymous', async () => {
    stubApi([['GET', '/api/auth/me', () => jsonResponse(500, { error: 'internal_error', message: 'Down.' })]])
    saveSession(TOKENS)
    renderProvider()
    await screen.findByRole('alert')

    sessionStorage.clear()
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
  })

  it('signs out locally first and revokes the refresh token best-effort', async () => {
    const fetch = stubApi([
      ['GET', '/api/auth/me', () => jsonResponse(200, EMPLOYEE)],
      ['POST', '/api/auth/logout', () => jsonResponse(400, { error: 'validation_error', message: 'Unknown token.' })],
    ])
    saveSession(TOKENS)
    renderProvider()
    await screen.findByText('Signed in as Eve Employee')

    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))

    expect(screen.getByTestId('status')).toHaveTextContent('anonymous')
    expect(readSession()).toBeNull()
    const logout = fetch.mock.calls.find(([url]) => String(url).endsWith('/api/auth/logout'))
    expect(JSON.parse(logout[1].body)).toEqual({ refresh_token: 'refresh' })
    // The failed revoke changes nothing: no error, still anonymous.
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('loads the user when a session appears later, and keeps them across a rotation', async () => {
    const fetch = stubApi([['GET', '/api/auth/me', () => jsonResponse(200, EMPLOYEE)]])
    renderProvider()
    expect(screen.getByTestId('status')).toHaveTextContent('anonymous')

    act(() => {
      saveSession(TOKENS)
    })
    expect(await screen.findByText('Signed in as Eve Employee')).toBeInTheDocument()

    // A refresh rotation saves new tokens; the user is already known.
    act(() => {
      saveSession({ ...TOKENS, access_token: 'rotated' })
    })
    expect(screen.getByTestId('status')).toHaveTextContent('signed-in')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
