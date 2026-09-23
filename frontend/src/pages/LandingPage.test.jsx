import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import LandingPage from './LandingPage'
import { renderPage } from '../test/helpers'

describe('LandingPage', () => {
  it('leads with the pitch and the two actions a visitor has', () => {
    renderPage(<LandingPage />, { path: '/' })
    expect(
      screen.getByRole('heading', { level: 1, name: 'Something broken at work? Report it in a minute.' }),
    ).toBeInTheDocument()
    const register = screen.getAllByRole('link', { name: 'Create an account' })
    const signIn = screen.getAllByRole('link', { name: 'Sign in' })
    expect(register.length).toBeGreaterThanOrEqual(2)
    expect(signIn.length).toBeGreaterThanOrEqual(2)
    expect(register.every((link) => link.getAttribute('href') === '/register')).toBe(true)
    expect(signIn.every((link) => link.getAttribute('href') === '/login')).toBe(true)
  })

  it('explains the workflow, the roles and the response targets', () => {
    renderPage(<LandingPage />, { path: '/' })
    expect(screen.getByRole('heading', { level: 2, name: 'From report to fix, in three steps' })).toBeInTheDocument()
    expect(
      screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent),
    ).toEqual([
      'Report it',
      'Facilities triages it',
      'You confirm the fix',
      'Employees',
      'Engineers',
      'Facility Admins',
    ])
    const targets = screen.getByRole('heading', { level: 2, name: 'Response targets you can hold us to' }).closest('section')
    expect(within(targets).getAllByRole('term').map((term) => term.textContent)).toEqual([
      'Critical',
      'High',
      'Medium',
      'Low',
    ])
    expect(within(targets).getAllByRole('definition').map((item) => item.textContent)).toEqual([
      '4 hours',
      '24 hours',
      '3 days',
      '7 days',
    ])
  })

  it('states the registration rule so nobody tries a personal address', () => {
    renderPage(<LandingPage />, { path: '/' })
    expect(screen.getByText(/Any @acme\.inc address can register/)).toBeInTheDocument()
  })
})
