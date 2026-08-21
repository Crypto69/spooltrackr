// End-to-end smoke test against a running backend in mock printer mode.
//   cd backend && .venv/bin/uvicorn app.main:app --port 8000   (with a fresh DB)
//   cd frontend && npx playwright test
import { test, expect } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

test('inventory shows the seeded spools', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'My filament' })).toBeVisible()
  await expect(page.locator('[data-test^="spool-"]')).toHaveCount(14)
  await page.getByTestId('search').or(page.locator('[data-test=search]')).fill('jade')
  await expect(page.locator('[data-test^="spool-"]')).toHaveCount(1)
})

test('sort by strength and heat resistance', async ({ page }) => {
  await page.goto('/')
  const cards = page.locator('[data-test^="spool-"]')
  await page.locator('[data-test=sort]').selectOption('strength')
  await expect(cards.first()).toContainText('PAHT-CF')
  await expect(cards.last()).toContainText('TPU')  // no strength spec -> last
  await page.locator('[data-test=sort]').selectOption('toughness')
  await expect(cards.first()).toContainText('TPU')  // TPU is the toughest
  await page.locator('[data-test=sort]').selectOption('stiffness')
  await expect(cards.first()).toContainText('PAHT-CF')
  await page.locator('[data-test=sort]').selectOption('heat')
  await expect(cards.first()).toContainText('PAHT-CF')
  await expect(cards.nth(1)).toContainText('PC')
})

test('compare up to four spools side by side', async ({ page }) => {
  await page.goto('/')
  await page.locator('[data-test=compare-toggle]').click()
  const cards = page.locator('[data-test^="spool-"]')
  for (let i = 0; i < 5; i++) await cards.nth(i).click()   // 5th is refused
  await expect(page.locator('[data-test=compare-bar] .badge')).toHaveCount(4)
  await page.locator('[data-test=compare-open]').click()
  const table = page.locator('[data-test=compare-table]')
  await expect(table.locator('thead th')).toHaveCount(5)   // label col + 4 spools
  await expect(table.getByRole('row', { name: /Heat resistance/ })).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
  await page.locator('[data-test=compare-toggle]').click()   // Done
  await expect(page.locator('[data-test=compare-bar]')).toHaveCount(0)
})

test('identify an AMS slot, print, and see grams deducted', async ({ page }) => {
  await page.goto('/ams')
  const a1 = page.locator('[data-test=slot-A1]')
  await expect(a1).toContainText('PLA Basic')
  const identify = a1.locator('[data-test=identify-A1]')
  if (await identify.isVisible()) {
    await identify.click()
    await page.locator('[data-test^="cand-"]').first().click()
  }
  await expect(a1).toContainText('Jade White')
  await expect(a1).toContainText('RFID')

  // Drive the mock printer through the API (same thing the dev buttons do)
  const before = await (await page.request.get('/api/ams')).json()
  const spoolId = before[0].spool.id
  const gBefore = before[0].spool.remaining_g
  await page.request.post('/api/debug/mock/start', { data: { name: 'e2e print', filaments: [{ type: 'PLA', color: 'FFFFFF', used_g: 12.5 }] } })
  await expect(page.locator('[data-test=printer-status]')).toContainText('Printing', { timeout: 5000 })
  await page.request.post('/api/debug/mock/finish', { data: {} })
  await expect(page.locator('[data-test=printer-status]')).not.toContainText('Printing', { timeout: 5000 })

  await page.goto(`/spools/${spoolId}`)
  await expect(page.getByText(`${(gBefore - 12.5).toFixed(1)} g`)).toBeVisible()
  await expect(page.getByText('e2e print')).toBeVisible()
})

test('manual weight adjustment is recorded', async ({ page }) => {
  const spools = await (await page.request.get('/api/spools')).json()
  const s = spools.find((x) => x.location === 'stored' && x.starting_weight_g >= 1000)
  await page.goto(`/spools/${s.id}`)
  await page.locator('[data-test=adjust]').click()
  await page.locator('[data-test=adjust-remaining]').fill('640')
  await page.locator('[data-test=adjust-save]').click()
  await expect(page.getByText('640.0 g')).toBeVisible()
  await expect(page.getByText('Adjusted')).toBeVisible()
})

test('failed print can be resolved from the Prints page', async ({ page }) => {
  await page.request.post('/api/debug/mock/start', { data: { name: 'e2e failed', filaments: [{ type: 'PLA', color: 'FFFFFF', used_g: 40 }] } })
  await page.request.post('/api/debug/mock/progress', { data: { pct: 25 } })
  await page.request.post('/api/debug/mock/fail', { data: {} })
  await page.goto('/prints')
  const card = page.locator('[data-test^="print-"]', { hasText: 'e2e failed' })
  await expect(card).toContainText('unresolved')
  await card.locator('[data-test^="resolve-"]').click()
  await page.locator('[data-test=resolve-apply]').click()
  await expect(card).toContainText('resolved')
  await expect(card).toContainText('10.0 g')
})

test('settings page saves', async ({ page }) => {
  await page.goto('/settings')
  await page.locator('[data-test=printer-mode]').selectOption('mock')
  await page.locator('[data-test=save-settings]').click()
  await expect(page.getByText('Settings saved')).toBeVisible()
})
