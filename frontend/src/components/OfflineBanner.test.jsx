import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import OfflineBanner from './OfflineBanner'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('OfflineBanner', () => {
  it('stays quiet while online and speaks up when the connection drops', async () => {
    render(<OfflineBanner />)
    expect(screen.queryByRole('status')).not.toBeInTheDocument()

    act(() => {
      window.dispatchEvent(new Event('offline'))
    })
    expect(screen.getByRole('status')).toHaveTextContent('You are offline')

    act(() => {
      window.dispatchEvent(new Event('online'))
    })
    await waitFor(() => expect(screen.queryByRole('status')).not.toBeInTheDocument())
  })

  it('starts shown when the page loads offline', () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    render(<OfflineBanner />)
    expect(screen.getByRole('status')).toHaveTextContent('You are offline')
  })
})
