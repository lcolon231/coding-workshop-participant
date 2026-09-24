import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ErrorBoundary from './ErrorBoundary'

function Bomb({ armed }) {
  if (armed) throw new Error('kaboom')
  return <p>All good</p>
}

let consoleError

beforeEach(() => {
  consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  consoleError.mockRestore()
})

describe('ErrorBoundary', () => {
  it('renders its children while nothing throws', () => {
    render(
      <ErrorBoundary>
        <Bomb armed={false} />
      </ErrorBoundary>,
    )
    expect(screen.getByText('All good')).toBeInTheDocument()
  })

  it('replaces a throwing tree with an alert and logs the error', () => {
    render(
      <ErrorBoundary>
        <Bomb armed />
      </ErrorBoundary>,
    )
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('Something went wrong')
    expect(screen.queryByText('kaboom')).not.toBeInTheDocument()
    expect(consoleError).toHaveBeenCalledWith('Unhandled render error', expect.any(Error), expect.anything())
  })

  it('tries again by remounting the children', async () => {
    let armed = true
    function Flaky() {
      return <Bomb armed={armed} />
    }
    render(
      <ErrorBoundary>
        <Flaky />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('alert')).toBeInTheDocument()
    armed = false
    await userEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(screen.getByText('All good')).toBeInTheDocument()
  })
})
