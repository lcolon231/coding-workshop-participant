import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import App from './App'
import { AuthContext } from './auth/AuthContext'
import { theme } from './theme'

function renderWith(auth, path) {
  return render(
    <ThemeProvider theme={theme}>
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </AuthContext.Provider>
    </ThemeProvider>,
  )
}

function renderAnonymous(path) {
  return renderWith({ status: 'anonymous', user: null, error: null, signOut: vi.fn(), retry: vi.fn() }, path)
}

describe('App, signed out', () => {
  it('shows the landing page at the root', () => {
    renderAnonymous('/')
    expect(screen.getByRole('heading', { level: 1, name: /Something broken at work/ })).toBeInTheDocument()
  })

  it('still sends a deep link to sign in', () => {
    renderAnonymous('/incidents/inc-1')
    expect(screen.getByRole('heading', { level: 1, name: /Sign in/ })).toBeInTheDocument()
    expect(screen.queryByText(/Something broken at work/)).not.toBeInTheDocument()
  })
})

describe('App, while the account loads', () => {
  it('shows the frame of the page rather than a flash of the sign-in screen', () => {
    renderWith({ status: 'loading', user: null, error: null, signOut: vi.fn(), retry: vi.fn() }, '/incidents/inc-1')
    expect(screen.getByLabelText('Loading your account')).toHaveAttribute('aria-busy', 'true')
    expect(screen.queryByText(/Sign in/)).not.toBeInTheDocument()
  })

  it('explains a failed account load and offers to retry or sign out', async () => {
    const auth = { status: 'error', user: null, error: 'Database unavailable.', signOut: vi.fn(), retry: vi.fn() }
    renderWith(auth, '/')
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load your account')
    expect(screen.getByRole('alert')).toHaveTextContent('Database unavailable.')

    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(auth.retry).toHaveBeenCalledTimes(1)
    await userEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    expect(auth.signOut).toHaveBeenCalledTimes(1)
  })
})
