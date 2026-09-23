import { describe, expect, it } from 'vitest'
import { humanise, splitDetails } from './formErrors'

describe('humanise', () => {
  it('strips the Pydantic prefix and makes a sentence', () => {
    expect(humanise('Value error, must be an @acme.inc address')).toBe(
      'Must be an @acme.inc address.',
    )
  })

  it('leaves a finished sentence alone', () => {
    expect(humanise('Building does not exist.')).toBe('Building does not exist.')
  })

  it('falls back when the message is missing', () => {
    expect(humanise(undefined)).toBe('Invalid value.')
  })
})

describe('splitDetails', () => {
  const fields = ['email', 'password']

  it('routes known fields inline and the rest to the form', () => {
    const { fieldErrors, formErrors } = splitDetails(
      [
        { field: 'email', message: 'value is not a valid email address' },
        { field: '__root__', message: 'Extra inputs are not permitted' },
        { field: 'role', message: 'Extra inputs are not permitted' },
      ],
      fields,
    )
    expect(fieldErrors).toEqual({ email: 'Value is not a valid email address.' })
    expect(formErrors).toEqual([
      'Extra inputs are not permitted.',
      'role: Extra inputs are not permitted.',
    ])
  })

  it('keeps only the first message per field', () => {
    const { fieldErrors } = splitDetails(
      [
        { field: 'password', message: 'too short' },
        { field: 'password', message: 'too weak' },
      ],
      fields,
    )
    expect(fieldErrors.password).toBe('Too short.')
  })

  it('tolerates a missing details list', () => {
    expect(splitDetails(undefined, fields)).toEqual({ fieldErrors: {}, formErrors: [] })
  })
})
