import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { useRef } from 'react'
import { useWidth } from './useWidth'

function Probe({ initial }) {
  const ref = useRef(null)
  const width = useWidth(ref, initial)
  return <div ref={ref}>{width}</div>
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('useWidth', () => {
  it('reports the initial width where ResizeObserver is missing', () => {
    render(<Probe initial={320} />)
    expect(screen.getByText('320')).toBeInTheDocument()
  })

  it('follows the observed element and ignores a zero width, then disconnects', () => {
    const observers = []
    class FakeResizeObserver {
      constructor(callback) {
        this.callback = callback
        this.observe = vi.fn()
        this.disconnect = vi.fn()
        observers.push(this)
      }
    }
    vi.stubGlobal('ResizeObserver', FakeResizeObserver)

    const { unmount } = render(<Probe initial={640} />)
    const [observer] = observers
    expect(observer.observe).toHaveBeenCalledWith(screen.getByText('640'))

    act(() => observer.callback([{ contentRect: { width: 511.6 } }]))
    expect(screen.getByText('512')).toBeInTheDocument()

    // A hidden element measures zero; the last real width stays.
    act(() => observer.callback([{ contentRect: { width: 0 } }]))
    expect(screen.getByText('512')).toBeInTheDocument()
    act(() => observer.callback([]))
    expect(screen.getByText('512')).toBeInTheDocument()

    unmount()
    expect(observer.disconnect).toHaveBeenCalled()
  })
})
