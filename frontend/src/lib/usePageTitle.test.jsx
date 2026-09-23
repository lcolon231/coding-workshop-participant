import { describe, expect, it } from 'vitest'
import { render } from '@testing-library/react'
import { pageTitle, usePageTitle } from './usePageTitle'

function Titled({ title }) {
  usePageTitle(title)
  return null
}

describe('usePageTitle', () => {
  it('formats a page title after the app name, or just the app name', () => {
    expect(pageTitle('Reports')).toBe('Reports · ACME Facility Incidents')
    expect(pageTitle()).toBe('ACME Facility Incidents')
  })

  it('sets the document title and follows changes', () => {
    const { rerender } = render(<Titled title="Users" />)
    expect(document.title).toBe('Users · ACME Facility Incidents')
    rerender(<Titled title="Aircon dripping" />)
    expect(document.title).toBe('Aircon dripping · ACME Facility Incidents')
  })
})
