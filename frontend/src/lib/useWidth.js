import { useEffect, useState } from 'react'

/**
 * The rendered width of an element, so an SVG chart can lay itself out in
 * real pixels and keep its text crisp instead of scaling a fixed viewBox.
 *
 * Falls back to `initial` where `ResizeObserver` is missing (jsdom).
 */
export function useWidth(ref, initial = 640) {
  const [width, setWidth] = useState(initial)
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0)
      if (next > 0) setWidth(next)
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return width
}
