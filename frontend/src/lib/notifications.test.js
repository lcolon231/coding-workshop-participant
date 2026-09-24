import { describe, expect, it } from 'vitest'
import { describeNotification } from './notifications'

const actor = { id: 'u-admin', full_name: 'Ada Admin', role: 'Facility Admin' }

describe('describeNotification', () => {
  it('names who assigned the work', () => {
    expect(describeNotification({ kind: 'Assigned', actor, incident_title: 'Lift stuck' })).toBe(
      'Ada Admin assigned you “Lift stuck”',
    )
  })

  it('names who reported the incident', () => {
    expect(
      describeNotification({ kind: 'Reported', actor: { full_name: 'Eve' }, incident_title: 'Leak' }),
    ).toBe('Eve reported “Leak”')
  })

  it('still reads when the actor is gone', () => {
    expect(describeNotification({ kind: 'Assigned', actor: null, incident_title: 'Leak' })).toBe(
      'You were assigned “Leak”',
    )
    expect(describeNotification({ kind: 'Reported', actor: null, incident_title: 'Leak' })).toBe(
      'New incident: “Leak”',
    )
  })

  it('tells the reporter about the outcome', () => {
    const engineer = { full_name: 'Hank Vance' }
    expect(describeNotification({ kind: 'Resolved', actor: engineer, incident_title: 'Leak' })).toBe(
      'Hank Vance resolved “Leak”',
    )
    expect(describeNotification({ kind: 'Closed', actor, incident_title: 'Leak' })).toBe(
      'Ada Admin closed “Leak”',
    )
    expect(describeNotification({ kind: 'Resolved', actor: null, incident_title: 'Leak' })).toBe(
      '“Leak” was resolved',
    )
    expect(describeNotification({ kind: 'Closed', actor: null, incident_title: 'Leak' })).toBe(
      '“Leak” was closed',
    )
  })

  it('falls back to the title for a kind it does not know', () => {
    expect(describeNotification({ kind: 'Other', actor, incident_title: 'Leak' })).toBe('“Leak”')
  })
})
