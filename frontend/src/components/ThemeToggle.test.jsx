import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThemeProvider } from '@mui/material/styles'
import { theme } from '../theme'
import ThemeToggle from './ThemeToggle'

function renderToggle() {
  return render(
    <ThemeProvider theme={theme}>
      <ThemeToggle />
    </ThemeProvider>,
  )
}

describe('ThemeToggle', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('offers the dark theme when the app is light', () => {
    renderToggle()
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
  })

  it('switches the scheme and remembers the choice', async () => {
    const user = userEvent.setup()
    renderToggle()
    await user.click(screen.getByRole('button', { name: 'Switch to dark theme' }))
    expect(await screen.findByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()
    expect(localStorage.getItem('mui-mode')).toBe('dark')
    await waitFor(() => expect(document.documentElement).toHaveAttribute('data-dark'))

    await user.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    expect(await screen.findByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
    expect(localStorage.getItem('mui-mode')).toBe('light')
    await waitFor(() => expect(document.documentElement).not.toHaveAttribute('data-dark'))
  })

  it('starts from a remembered dark choice', () => {
    localStorage.setItem('mui-mode', 'dark')
    renderToggle()
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()
  })
})
