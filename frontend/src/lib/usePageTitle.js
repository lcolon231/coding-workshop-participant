import { useEffect } from 'react'

export const APP_NAME = 'ACME Facility Incidents'

/** The browser title for a page: "Reports · ACME Facility Incidents", or just the app. */
export function pageTitle(title) {
  return title ? `${title} · ${APP_NAME}` : APP_NAME
}

/**
 * Give the page a title of its own.
 *
 * A single-page app otherwise keeps one title for every screen, so the tab,
 * the history list and a screen reader's page announcement all say the same
 * thing wherever the visitor is (WCAG 2.4.2). Pass what the page's `h1` says.
 */
export function usePageTitle(title) {
  useEffect(() => {
    document.title = pageTitle(title)
  }, [title])
}
