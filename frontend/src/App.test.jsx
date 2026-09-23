import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import App from './App'
import { AuthContext } from './auth/AuthContext'
import { theme } from './theme'

function renderAnonymous(path) {
  const auth = { status: 'anonymous', user: null, error: null, signOut: vi.fn(), retry: vi.fn() }
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
