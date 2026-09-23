import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * Move focus to the page after the route changes.
 *
 * A link in a single-page app swaps the content but leaves focus where it
 * was, so a screen reader says nothing and the next Tab lands somewhere in
 * the old bar. Focusing the `main` landmark (which carries `tabIndex={-1}`)
 * announces the new page from its top and puts the next Tab inside it. Only
 * the path counts: a filter that changes the query string is not a new page,
 * and the very first render is the browser's own load.
 */
export default function RouteFocus() {
  const { pathname } = useLocation()
  const previous = useRef(pathname)
  useEffect(() => {
    if (previous.current === pathname) return
    previous.current = pathname
    document.getElementById('main')?.focus({ preventScroll: false })
  }, [pathname])
  return null
}
