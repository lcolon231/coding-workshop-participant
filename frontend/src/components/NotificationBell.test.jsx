import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import NotificationBell from './NotificationBell'
import { POLL_INTERVAL_MS } from '../lib/notifications'
import { ADMIN, ENGINEER, EMPLOYEE, calls, jsonResponse, renderSignedIn, signIn, stubApi } from '../test/helpers'

const BASE = '/api/incidents/notifications'

function notification(overrides = {}) {
  return {
    id: 'n-1',
    kind: 'Assigned',
    incident_id: 'inc-1',
    incident_title: 'Aircon dripping',
    actor: ADMIN,
    read_at: null,
    created_at: new Date(Date.now() - 5 * 60_000).toISOString(),
    ...overrides,
  }
}

function stubNotifications(items, extra = {}) {
  const unread = items.filter((item) => !item.read_at).length
  return stubApi([
    [
      'GET',
      BASE,
      () =>
        jsonResponse(200, {
          items,
          total: items.length,
          limit: 10,
          offset: 0,
          unread_count: extra.unread_count ?? unread,
        }),
    ],
    ['POST', `${BASE}/read-all`, () => new Response(null, { status: 204 })],
    [
      'POST',
      /^\/api\/incidents\/notifications\/[^/]+\/read$/,
      () => jsonResponse(200, notification({ read_at: new Date().toISOString() })),
    ],
  ])
}

function renderBell(user = ENGINEER) {
  signIn()
  return renderSignedIn(<NotificationBell />, { path: '/', user })
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('NotificationBell', () => {
  it('loads on mount and shows the unread count', async () => {
    const fetch = stubNotifications([notification(), notification({ id: 'n-2', read_at: '2026-09-22T10:00:00Z' })])
    renderBell()
    expect(await screen.findByRole('button', { name: 'Notifications, 1 unread' })).toBeInTheDocument()
    expect(calls(fetch)).toEqual([`GET ${BASE}?limit=10`])
  })

  it('opens a menu that phrases each notification and marks it read on the way to the incident', async () => {
    const user = userEvent.setup()
    const fetch = stubNotifications([
      notification(),
      notification({
        id: 'n-2',
        kind: 'Reported',
        incident_id: 'inc-2',
        incident_title: 'Lift stuck',
        actor: EMPLOYEE,
        read_at: '2026-09-22T10:00:00Z',
        created_at: new Date(Date.now() - 26 * 3600_000).toISOString(),
      }),
    ])
    renderBell(ADMIN)
    await user.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }))

    const menu = screen.getByRole('menu')
    const items = within(menu).getAllByRole('menuitem')
    expect(items.map((item) => item.textContent)).toEqual([
      'Ada Admin assigned you “Aircon dripping” (unread)5 minutes ago',
      'Eve Employee reported “Lift stuck”yesterday',
    ])

    await user.click(items[0])
    expect(await screen.findByText('Detail stub')).toBeInTheDocument()
    await waitFor(() => expect(calls(fetch)).toContain(`POST ${BASE}/n-1/read`))
  })

  it('marks everything read from the menu', async () => {
    const user = userEvent.setup()
    const fetch = stubNotifications([notification(), notification({ id: 'n-2' })])
    renderBell()
    await user.click(await screen.findByRole('button', { name: 'Notifications, 2 unread' }))
    await user.click(screen.getByRole('button', { name: 'Mark all as read' }))

    await waitFor(() => expect(calls(fetch)).toContain(`POST ${BASE}/read-all`))
    expect(screen.getByRole('button', { name: 'Mark all as read' })).toBeDisabled()
    expect(within(screen.getByRole('menu')).queryByText('(unread)')).not.toBeInTheDocument()
    // The open menu hides the bar from assistive tech, hence `hidden`.
    expect(screen.getByRole('button', { name: 'Notifications', hidden: true })).toBeInTheDocument()
  })

  it('says when there is nothing', async () => {
    const user = userEvent.setup()
    stubNotifications([])
    renderBell()
    await user.click(await screen.findByRole('button', { name: 'Notifications' }))
    expect(screen.getByText('You’re all caught up.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Mark all as read' })).toBeDisabled()
  })

  it('polls while the tab is visible and refreshes on focus', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const fetch = stubNotifications([])
    renderBell()
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(1))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS)
    })
    expect(fetch).toHaveBeenCalledTimes(2)

    act(() => {
      window.dispatchEvent(new Event('focus'))
    })
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(3))
  })

  it('keeps what it last showed when a poll fails', async () => {
    const user = userEvent.setup()
    let failing = false
    const fetch = stubApi([
      [
        'GET',
        BASE,
        () =>
          failing
            ? jsonResponse(503, { error: 'unavailable', message: 'Down' })
            : jsonResponse(200, { items: [notification()], total: 1, limit: 10, offset: 0, unread_count: 1 }),
      ],
    ])
    renderBell()
    await screen.findByRole('button', { name: 'Notifications, 1 unread' })
    failing = true
    await user.click(screen.getByRole('button', { name: 'Notifications, 1 unread' }))
    await waitFor(() => expect(fetch.mock.calls.length).toBeGreaterThanOrEqual(2))
    expect(within(screen.getByRole('menu')).getAllByRole('menuitem')).toHaveLength(1)
  })
})
