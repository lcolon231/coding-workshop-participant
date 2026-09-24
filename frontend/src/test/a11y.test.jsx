import { afterEach, describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { axe } from 'vitest-axe'
import * as matchers from 'vitest-axe/matchers'
import { vi } from 'vitest'
import AppShell from '../components/AppShell'
import EscalationsPage from '../pages/EscalationsPage'
import FacilitiesPage from '../pages/FacilitiesPage'
import IncidentPage from '../pages/IncidentPage'
import IncidentsPage from '../pages/IncidentsPage'
import LandingPage from '../pages/LandingPage'
import LoginPage from '../pages/LoginPage'
import NewIncidentPage from '../pages/NewIncidentPage'
import RegisterPage from '../pages/RegisterPage'
import ReportsPage from '../pages/ReportsPage'
import UsersPage from '../pages/UsersPage'
import {
  ADMIN,
  EMPLOYEE,
  ENGINEER,
  incidentFixture,
  jsonResponse,
  page,
  renderPage,
  renderSignedIn,
  signIn,
  stubApi,
  userFixture,
} from './helpers'

expect.extend(matchers)

/**
 * axe over every screen, rendered as the page tests render them.
 *
 * jsdom lays nothing out, so colour contrast cannot be judged here; the
 * theme's pairs were computed by hand for T91 (all above 5:1). Everything
 * else axe checks in the DOM applies: names, roles, landmarks, lists,
 * headings, duplicate ids, ARIA attribute validity.
 */
const OPTIONS = { rules: { 'color-contrast': { enabled: false } } }

const INCIDENT = incidentFixture({
  assignee_id: ENGINEER.id,
  assignee: ENGINEER,
  status: 'In Progress',
  allowed_transitions: [{ to: 'Resolved', label: 'Resolve', requires: ['resolution_note'] }],
})

const NOTIFICATIONS = ['GET', '/api/incidents/notifications', () =>
  jsonResponse(200, { items: [], total: 0, limit: 10, offset: 0, unread_count: 0 })]

function facilityLists() {
  return [
    ['GET', '/api/facilities/buildings', () => jsonResponse(200, page([{ id: 'b-1', code: 'HQ', name: 'Headquarters', address: null, is_active: true }]))],
    ['GET', '/api/facilities/categories', () => jsonResponse(200, page([{ id: 'c-1', name: 'HVAC', parent_id: null, is_active: true }]))],
    ['GET', /^\/api\/facilities\/buildings\/.+\/floors$/, () => jsonResponse(200, page([]))],
    ['GET', /^\/api\/facilities\/floors\/.+\/seats$/, () => jsonResponse(200, page([]))],
    ['GET', '/api/facilities/engineers', () => jsonResponse(200, page([]))],
    ['GET', /^\/api\/facilities\/(buildings|floors|seats|categories)\/[^/]+$/, () =>
      jsonResponse(200, { id: 'b-1', code: 'HQ', name: 'Headquarters', address: null, is_active: true, level: 3, building_id: 'b-1' })],
  ]
}

afterEach(() => {
  vi.unstubAllGlobals()
})

async function expectClean(container) {
  expect(await axe(container, OPTIONS)).toHaveNoViolations()
}

describe('accessibility (axe)', () => {
  it('landing page', async () => {
    const { container } = renderPage(<LandingPage />, { path: '/' })
    await expectClean(container)
  })

  it('sign in and register', async () => {
    const login = renderPage(<LoginPage />, { path: '/login' })
    await expectClean(login.container)
    login.unmount()
    const register = renderPage(<RegisterPage />, { path: '/register' })
    await expectClean(register.container)
  })

  it('app shell with the bell', async () => {
    signIn()
    stubApi([NOTIFICATIONS])
    const { container } = renderSignedIn(<AppShell />, { path: '/', user: ENGINEER })
    await screen.findByRole('button', { name: 'Notifications' })
    await expectClean(container)
  })

  it('incident list', async () => {
    signIn()
    stubApi([['GET', '/api/incidents', () => jsonResponse(200, page([incidentFixture(), INCIDENT]))]])
    const { container } = renderSignedIn(<IncidentsPage />, { path: '/', user: EMPLOYEE })
    await screen.findByText('Showing 1 to 2 of 2')
    await expectClean(container)
  })

  it('incident detail', async () => {
    signIn()
    stubApi([
      ['GET', '/api/incidents/inc-1', () => jsonResponse(200, INCIDENT)],
      ['GET', /^\/api\/incidents\/inc-1\/(history|notes|escalations)$/, () => jsonResponse(200, page([]))],
      ...facilityLists(),
    ])
    const { container } = renderSignedIn(<IncidentPage />, {
      path: '/incidents/:incidentId',
      initialEntries: ['/incidents/inc-1'],
      user: ENGINEER,
    })
    await screen.findByRole('heading', { level: 1, name: INCIDENT.title })
    await expectClean(container)
  })

  it('report form', async () => {
    signIn()
    stubApi(facilityLists())
    const { container } = renderSignedIn(<NewIncidentPage />, { path: '/incidents/new', user: EMPLOYEE })
    await screen.findByRole('option', { name: 'HQ, Headquarters' })
    await expectClean(container)
  })

  it('users', async () => {
    signIn()
    stubApi([['GET', '/api/auth/users', () => jsonResponse(200, page([userFixture(), userFixture({ id: 'u-admin', email: 'admin@acme.inc', role: 'Facility Admin', occupation: null })]))]])
    const { container } = renderSignedIn(<UsersPage />, { path: '/users', user: ADMIN })
    await screen.findByText('Showing 1 to 2 of 2')
    await expectClean(container)
  })

  it('escalation queue', async () => {
    signIn()
    stubApi([['GET', '/api/incidents/escalations', () => jsonResponse(200, page([{ id: 'e-1', incident_id: 'inc-1', incident_title: 'Aircon dripping', incident_status: 'Open', incident_priority: 'Low', requested_by: EMPLOYEE, reason: 'The whole row cannot work.', status: 'Pending', decided_by: null, decided_at: null, decision_note: null, created_at: '2026-09-22T11:00:00Z' }]))]])
    const { container } = renderSignedIn(<EscalationsPage />, { path: '/escalations', user: ADMIN })
    await screen.findByRole('button', { name: 'Approve' })
    await expectClean(container)
  })

  it('facilities', async () => {
    signIn()
    stubApi(facilityLists())
    const { container } = renderSignedIn(<FacilitiesPage />, { path: '/facilities', user: ADMIN })
    await screen.findByText('HQ · Headquarters')
    await expectClean(container)
  })

  it('reports, including their failed-load states', async () => {
    signIn()
    stubApi([
      ['GET', '/api/incidents/reports/summary', () =>
        jsonResponse(200, { date_from: '2026-08-24', date_to: '2026-09-23', total: 0, by_status: [], by_priority: [], backlog_by_age: [] })],
      ['GET', /^\/api\/incidents\/reports\/(sla|volume)$/, () => jsonResponse(503, { error: 'unavailable', message: 'Down.' })],
      ...facilityLists(),
    ])
    const { container } = renderSignedIn(<ReportsPage />, { path: '/reports', user: ADMIN })
    await screen.findAllByText('Down.')
    await expectClean(container)
  })
})
