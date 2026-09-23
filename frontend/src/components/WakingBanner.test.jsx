import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import WakingBanner from './WakingBanner'
import { resetReadiness, waitUntilReady } from '../services/readiness'
import { jsonResponse } from '../test/helpers'

beforeEach(() => {
  vi.useFakeTimers()
  resetReadiness()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('WakingBanner', () => {
  it('shows while the API client waits for the database and counts the seconds', async () => {
    let ready = false
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(ready ? 200 : 503, { status: ready ? 'ready' : 'not_ready', database: ready, migrations_pending: false }),
      ),
    )
    render(<WakingBanner />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    let wait
    await act(async () => {
      wait = waitUntilReady({ intervalMs: 1000, deadlineMs: 90_000 })
      await vi.advanceTimersByTimeAsync(10)
    })
    expect(screen.getByRole('status')).toHaveTextContent('Waking the database')
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100)
    })
    expect(screen.getByRole('status')).toHaveTextContent('2s')

    ready = true
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
      await wait
    })
    // The toast slides out; its exit timer only exists once React has re-rendered.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })
})
