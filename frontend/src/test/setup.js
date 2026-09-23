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
 *
 * One stable function is installed once and only its behaviour is swapped:
 * React Responsive captures `window.matchMedia` when it is first imported,
 * so a function replaced per test would never be consulted.
 */
let currentMatch = () => false

export function mockViewport({ matches }) {
  currentMatch = typeof matches === 'function' ? matches : () => matches
}

const DESKTOP = (query) => {
  const width = /min-width:\s*(\d+)px/.exec(query)
  return width ? Number(width[1]) <= 1200 : false
}

Object.defineProperty(window, 'matchMedia', {
  configurable: true,
  writable: true,
  value: vi.fn((query) => ({
    get matches() {
      return currentMatch(query)
    },
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })),
})

mockViewport({ matches: DESKTOP })

afterEach(() => {
  cleanup()
  sessionStorage.clear()
  mockViewport({ matches: DESKTOP })
})
