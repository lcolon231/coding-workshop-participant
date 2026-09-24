import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { SlaChip } from './IncidentChips'
import { slaLabel } from '../lib/incidents'

const NOW = new Date('2026-09-23T10:00:00Z').getTime()

describe('slaLabel', () => {
  it('counts down while open, says how late once breached, and grades finished work', () => {
    expect(slaLabel({ sla_state: 'on_track', due_at: '2026-09-25T10:00:00Z' }, NOW)).toBe('Due in 2d')
    expect(slaLabel({ sla_state: 'at_risk', due_at: '2026-09-23T10:45:00Z' }, NOW)).toBe('Due in 45m')
    expect(slaLabel({ sla_state: 'breached', due_at: '2026-09-23T07:30:00Z' }, NOW)).toBe('Overdue by 2h 30m')
    expect(slaLabel({ sla_state: 'met', due_at: '2026-09-01T00:00:00Z' }, NOW)).toBe('Met target')
    expect(slaLabel({ sla_state: 'missed', due_at: '2026-09-01T00:00:00Z' }, NOW)).toBe('Missed target')
  })

  it('trusts the clock over a stale on_track when the deadline has since passed', () => {
    expect(slaLabel({ sla_state: 'on_track', due_at: '2026-09-23T09:59:00Z' }, NOW)).toBe('Overdue by 1m')
  })
})

describe('SlaChip', () => {
  it('draws nothing for a row without the field', () => {
    const { container } = render(<SlaChip incident={{ id: 'x' }} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('carries the deadline as its tooltip', () => {
    render(<SlaChip incident={{ sla_state: 'breached', due_at: '2026-09-23T07:30:00Z' }} now={NOW} />)
    expect(screen.getByText('Overdue by 2h 30m').closest('.MuiChip-root')).toHaveAttribute('title', expect.stringMatching(/^Target /))
  })
})
