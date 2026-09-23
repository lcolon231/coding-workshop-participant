import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Notice from './Notice'

describe('Notice', () => {
  it('announces a success politely', () => {
    render(<Notice notice="Incident reported." onClose={vi.fn()} />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Incident reported.')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('announces a failure as an alert that stays until dismissed', async () => {
    const onClose = vi.fn()
    render(<Notice notice={{ message: 'Building is still referenced.', severity: 'error' }} onClose={onClose} />)
    expect(screen.getByRole('alert')).toHaveTextContent('Building is still referenced.')
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('renders nothing without a notice', () => {
    render(<Notice notice={null} onClose={vi.fn()} />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
