import { expect, test } from '@playwright/test'
import { E2E_PASSWORD } from '../playwright.config'

/**
 * The critical path, end to end through the real UI and the real backend (T98):
 * an employee registers and reports an incident, an admin acknowledges it,
 * assigns an engineer and resolves it, and the reporter confirms and closes.
 *
 * The backend is the throwaway one from `tools/e2e_backend.py`, so the seed
 * admin signs in with the seed password and nothing here touches a
 * development database.
 */
const ADMIN_EMAIL = 'admin@acme.inc'

async function signIn(page, email, password = E2E_PASSWORD) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password', { exact: true }).fill(password)
  await page.locator('form button[type="submit"]').click()
  // Signed in lands wherever the visitor was headed, so assert the shell, not a page.
  await expect(page.getByRole('button', { name: 'Account menu' })).toBeVisible()
}

async function signOut(page) {
  await page.getByRole('button', { name: 'Account menu' }).click()
  await page.getByRole('menuitem', { name: 'Sign out' }).click()
  await expect(page).toHaveURL(/\/login$/)
}

/** Run one workflow move from the incident page and wait for its confirmation. */
async function transition(page, label, fill = async () => {}) {
  await page.getByRole('button', { name: label }).click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible()
  await fill(dialog)
  await dialog.getByRole('button', { name: label }).click()
  await expect(dialog).toBeHidden()
}

test('an incident goes from report to closed through the roles that own each step', async ({ page }) => {
  test.setTimeout(120_000)
  const stamp = Date.now()
  const reporter = `e2e.reporter.${stamp}@acme.inc`
  const title = `E2E: aircon dripping onto desk ${stamp}`

  // 1. A new employee registers and signs in.
  await page.goto('/register')
  await page.getByLabel('Full name').fill('Erin Endtoend')
  await page.getByLabel('Work email').fill(reporter)
  await page.getByLabel('Password', { exact: true }).fill(E2E_PASSWORD)
  await page.getByLabel('Occupation').fill('Analyst')
  await page.getByLabel('Date of birth').fill('1990-05-05')
  await page.locator('form button[type="submit"]').click()
  await expect(page).toHaveURL(/\/login$/)
  await expect(page.getByRole('alert')).toBeVisible()
  await signIn(page, reporter)

  // 2. They report an incident against a seeded building, floor and seat.
  await page.getByRole('link', { name: 'Report an incident' }).first().click()
  await expect(page).toHaveURL(/\/incidents\/new$/)
  await page.getByLabel('Title').fill(title)
  await page.getByLabel('Description').fill('Water on the desk since this morning. The ceiling tile is stained.')
  await page.getByLabel('Priority').selectOption('High')
  await page.getByLabel('Category').selectOption({ index: 1 })
  await page.getByLabel('Building').selectOption({ index: 1 })
  await page.getByLabel('Floor').selectOption({ index: 1 })
  await page.getByLabel('Seat').selectOption({ index: 1 })
  await page.locator('form button[type="submit"]').click()
  await expect(page).toHaveURL(/\/incidents\/[0-9a-f-]{36}$/)
  const incidentUrl = page.url()
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
  await expect(page.getByText('Incident reported.')).toBeVisible()
  // A reporter has no forward move on an open incident.
  await expect(page.getByRole('button', { name: 'Acknowledge and start work' })).toHaveCount(0)
  await signOut(page)

  // 3. The admin acknowledges it, assigning the seeded HVAC engineer, then resolves it.
  await signIn(page, ADMIN_EMAIL)
  await page.goto(incidentUrl)
  await expect(page.getByRole('heading', { level: 1, name: title })).toBeVisible()
  await transition(page, 'Acknowledge and start work', async (dialog) => {
    await dialog.getByLabel('Engineer').selectOption({ label: 'Hank Vance' })
  })
  await expect(page.getByText('Now In Progress.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Resolve' })).toBeVisible()
  await transition(page, 'Resolve', async (dialog) => {
    await dialog.getByLabel('Resolution note').fill('Drain line cleared and the tile replaced.')
  })
  await expect(page.getByText('Now Resolved.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Confirm and close' })).toBeVisible()
  await signOut(page)

  // 4. The reporter sees the resolution and closes the loop.
  await signIn(page, reporter)
  await page.goto('/')
  await page.getByRole('link', { name: title }).click()
  await expect(page).toHaveURL(incidentUrl)
  await expect(page.getByText('Drain line cleared and the tile replaced.').first()).toBeVisible()
  await transition(page, 'Confirm and close')
  await expect(page.getByText('Now Closed.')).toBeVisible()
  // Closed is terminal: nothing left to do.
  await expect(page.getByRole('heading', { name: 'Actions' })).toHaveCount(0)

  // 5. The list reflects the final state.
  await page.getByRole('link', { name: 'Incidents' }).first().click()
  const row = page.getByRole('row').filter({ hasText: title })
  await expect(row).toContainText('Closed')
})

test('a stranger cannot read someone else\'s incident', async ({ page, request }) => {
  // Visibility is 404, not 403: an employee who did not report it gets the same answer as a bad id.
  await signIn(page, 'second.employee@acme.inc')
  const token = await page.evaluate(() => JSON.parse(sessionStorage.getItem('acme.session')).accessToken)
  const mine = await request.get('/api/incidents', { headers: { authorization: `Bearer ${token}` } })
  expect(mine.status()).toBe(200)
  const everything = await request.get('/api/incidents?limit=100', { headers: { authorization: `Bearer ${token}` } })
  const ids = (await everything.json()).items.map((item) => item.id)

  const admin = await request.post('/api/auth/login', { data: { email: ADMIN_EMAIL, password: E2E_PASSWORD } })
  const adminToken = (await admin.json()).access_token
  const all = await request.get('/api/incidents?limit=100', { headers: { authorization: `Bearer ${adminToken}` } })
  const foreign = (await all.json()).items.find((item) => !ids.includes(item.id))
  expect(foreign).toBeTruthy()

  await page.goto(`/incidents/${foreign.id}`)
  await expect(page.getByRole('heading', { name: 'Incident not found' })).toBeVisible()
})
