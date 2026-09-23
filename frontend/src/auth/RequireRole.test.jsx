import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import RequireRole from './RequireRole'
import { ADMIN, EMPLOYEE, renderSignedIn } from '../test/helpers'

function renderGate(user) {
  return renderSignedIn(
    <RequireRole roles={['Facility Admin']}>
      <p>Admin only</p>
    </RequireRole>,
    { path: '/users', user },
  )
}

describe('RequireRole', () => {
  it('renders the screen for a listed role', () => {
    renderGate(ADMIN)
    expect(screen.getByText('Admin only')).toBeInTheDocument()
  })

  it('sends anyone else to the incident list', () => {
    renderGate(EMPLOYEE)
    expect(screen.getByText('Home stub')).toBeInTheDocument()
    expect(screen.queryByText('Admin only')).not.toBeInTheDocument()
  })
})
