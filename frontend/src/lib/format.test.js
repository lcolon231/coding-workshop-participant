import { describe, expect, it } from 'vitest'
import { formatDate, formatDuration, formatPercent, isoDate } from './format'

describe('formatDuration', () => {
  it('shows an em dash when nothing was measured', () => {
    expect(formatDuration(null)).toBe('—')
    expect(formatDuration(undefined)).toBe('—')
    expect(formatDuration(Number.NaN)).toBe('—')
  })

  it('picks the two largest units that matter', () => {
    expect(formatDuration(45)).toBe('45s')
    expect(formatDuration(12 * 60)).toBe('12m')
    expect(formatDuration(2 * 3600 + 15 * 60)).toBe('2h 15m')
    expect(formatDuration(3 * 3600)).toBe('3h')
    expect(formatDuration(3 * 86400 + 4 * 3600 + 59 * 60)).toBe('3d 4h')
    expect(formatDuration(7 * 86400)).toBe('7d')
  })
})

describe('formatPercent', () => {
  it('rounds a ratio to whole percent and dashes the unknown', () => {
    expect(formatPercent(0.8349)).toBe('83%')
    expect(formatPercent(1)).toBe('100%')
    expect(formatPercent(null)).toBe('—')
  })
})

describe('dates', () => {
  it('turns any date into the API form in UTC', () => {
    expect(isoDate(new Date('2026-09-22T23:30:00Z'))).toBe('2026-09-22')
    expect(isoDate('2026-01-05')).toBe('2026-01-05')
  })

  it('formats a calendar day without sliding across a timezone', () => {
    expect(formatDate('2026-09-22')).toMatch(/22/)
    expect(formatDate('2026-09-22')).toMatch(/2026/)
    expect(formatDate(null)).toBe('')
  })
})
