import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { configureReadiness } from '../services/readiness'

// A failed request probes readiness once and, in tests, never polls: the
// readiness tests pass their own deadline and interval explicitly.
configureReadiness({ deadlineMs: 0, intervalMs: 0 })

/**
 * jsdom has no `matchMedia`. Report a desktop viewport by default: any
 * `min-width` up to 1200px matches. A test that wants a phone passes
 * `{ matches: false }` through `mockViewport`.
 */
export function mockViewport({ matches }) {
  vi.stubGlobal(
    'matchMedia',
    vi.fn((query) => ({
      matches: typeof matches === 'function' ? matches(query) : matches,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    })),
  )
}

const DESKTOP = (query) => {
  const width = /min-width:\s*(\d+)px/.exec(query)
  return width ? Number(width[1]) <= 1200 : false
}

mockViewport({ matches: DESKTOP })

afterEach(() => {
  cleanup()
  sessionStorage.clear()
  mockViewport({ matches: DESKTOP })
})
