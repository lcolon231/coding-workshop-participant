import { describe, expect, it } from 'vitest'
import { loadLevel } from './users'

describe('loadLevel', () => {
  it.each([
    [0, 5, 'Low'],
    [2, 5, 'Low'],
    [3, 5, 'Medium'],
    [4, 5, 'Medium'],
    [5, 5, 'High'],
    [9, 5, 'High'],
    [0, 0, 'High'],
  ])('%i open of %i is %s', (open_assignments, max_concurrent_incidents, level) => {
    expect(loadLevel({ open_assignments, max_concurrent_incidents })).toBe(level)
  })
})
