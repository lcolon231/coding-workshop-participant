import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render } from '@testing-library/react'
import { vi } from 'vitest'
import { ThemeProvider } from '@mui/material/styles'
import { AuthContext } from '../auth/AuthContext'
import { theme } from '../theme'

/**
 * Render a page inside a router with stub destinations, so a test can assert
 * where the page navigated to and what state it carried.
 */
export function renderPage(element, { path, initialEntries = [path] }) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <Routes>
        <Route path={path} element={element} />
        <Route path="/" element={<p>Home stub</p>} />
        <Route path="/login" element={<LoginStub />} />
        <Route path="/register" element={<p>Register stub</p>} />
      </Routes>
    </MemoryRouter>,
  )
}

function LoginStub() {
  return <p>Login stub</p>
}

export const ADMIN = { id: 'u-admin', full_name: 'Ada Admin', role: 'Facility Admin' }
export const ENGINEER = { id: 'u-eng', full_name: 'Hank Vance', role: 'Engineer' }
export const EMPLOYEE = { id: 'u-emp', full_name: 'Eve Employee', role: 'Employee' }

/** Render a signed-in page: an auth context around a router with stub destinations. */
export function renderSignedIn(element, { path, initialEntries = [path], user = EMPLOYEE }) {
  const auth = { status: 'signed-in', user, error: null, signOut: vi.fn(), retry: vi.fn() }
  const view = render(
    <ThemeProvider theme={theme}>
      <AuthContext.Provider value={auth}>
        <MemoryRouter initialEntries={initialEntries}>
          <Routes>
            <Route path={path} element={element} />
            <Route path="/" element={<p>Home stub</p>} />
            <Route path="/incidents/new" element={<p>New incident stub</p>} />
            <Route path="/incidents/:id" element={<p>Detail stub</p>} />
            <Route path="/users" element={<p>Users stub</p>} />
            <Route path="/facilities" element={<p>Facilities stub</p>} />
            <Route path="/reports" element={<p>Reports stub</p>} />
            <Route path="/login" element={<LoginStub />} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    </ThemeProvider>,
  )
  return { ...view, auth }
}

/** A `fetch` response carrying the API's JSON envelope. */
export function jsonResponse(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'x-request-id': 'req-1', ...headers },
  })
}

/** One page of a collection. */
export function page(items, extra = {}) {
  return { items, total: items.length, limit: 25, offset: 0, ...extra }
}

/**
 * Stub `fetch` with route handlers: `[method, pattern, handler]`, where the
 * handler receives the parsed URL and the JSON body and returns a Response.
 * Anything unmatched is a JSON 404, the shape the dispatcher answers with.
 */
export function stubApi(routes) {
  const fetch = vi.fn(async (input, init = {}) => {
    const url = new URL(String(input), 'http://localhost')
    const method = (init.method ?? 'GET').toUpperCase()
    const body = init.body ? JSON.parse(init.body) : undefined
    for (const [routeMethod, pattern, handler] of routes) {
      if (routeMethod !== method) continue
      const match = typeof pattern === 'string' ? url.pathname === pattern : pattern.test(url.pathname)
      if (match) return handler({ url, body, init })
    }
    return jsonResponse(404, { error: 'not_found', message: `No route for ${method} ${url.pathname}` })
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

/** The calls `fetch` received, as `"METHOD /path?query"` strings. */
export function calls(fetch) {
  return fetch.mock.calls.map(([input, init]) => `${(init?.method ?? 'GET').toUpperCase()} ${input}`)
}

export function signIn() {
  sessionStorage.setItem(
    'acme.session',
    JSON.stringify({ accessToken: 'access-1', refreshToken: 'refresh-1', expiresAt: Date.now() + 1e6 }),
  )
}

/** A `UserOut` row as the admin list returns it. */
export function userFixture(overrides = {}) {
  return {
    id: 'u-emp',
    email: 'employee@acme.inc',
    full_name: 'Eve Employee',
    role: 'Employee',
    occupation: 'Financial Analyst',
    date_of_birth: '1995-01-30',
    is_active: true,
    created_at: '2026-09-01T09:00:00Z',
    ...overrides,
  }
}

export function incidentFixture(overrides = {}) {
  return {
    id: 'inc-1',
    title: 'Aircon dripping on desk 3-14',
    description: 'Water on the desk since 9am.\nThe ceiling tile is stained.',
    status: 'Open',
    priority: 'Medium',
    reporter_id: EMPLOYEE.id,
    reporter: EMPLOYEE,
    assignee_id: null,
    assignee: null,
    category_id: null,
    building_id: 'b-1',
    floor_id: 'f-3',
    seat_id: null,
    acknowledged_at: null,
    assigned_at: null,
    resolved_at: null,
    closed_at: null,
    resolution_note: null,
    blocked_reason: null,
    created_at: '2026-09-22T09:12:00Z',
    updated_at: '2026-09-22T09:12:00Z',
    allowed_transitions: [],
    ...overrides,
  }
}
