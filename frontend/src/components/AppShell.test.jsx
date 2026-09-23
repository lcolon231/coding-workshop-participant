import { describe, expect, it } from 'vitest'
import { screen, within } from '@testing-library/react'
import AppShell from './AppShell'
import { ADMIN, EMPLOYEE, ENGINEER, renderSignedIn } from '../test/helpers'

describe('AppShell', () => {
  it('shows the management links to an admin', () => {
    renderSignedIn(<AppShell />, { path: '/', user: ADMIN })
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((link) => link.textContent)).toEqual([
      'Incidents',
      'Users',
      'Facilities',
      'Reports',
    ])
    expect(within(nav).getByRole('link', { name: 'Reports' })).toHaveAttribute('href', '/reports')
  })

  it('shows only the incident list to everyone else', () => {
    renderSignedIn(<AppShell />, { path: '/', user: EMPLOYEE })
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link').map((link) => link.textContent)).toEqual(['Incidents'])
  })

  it('gives staff a notification bell and employees none', () => {
    renderSignedIn(<AppShell />, { path: '/', user: ENGINEER })
    expect(screen.getByRole('button', { name: 'Notifications' })).toBeInTheDocument()
  })

  it('shows no bell to an employee, who is never notified', () => {
    renderSignedIn(<AppShell />, { path: '/', user: EMPLOYEE })
    expect(screen.queryByRole('button', { name: /Notifications/ })).not.toBeInTheDocument()
  })
})
