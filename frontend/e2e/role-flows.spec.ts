import { expect, type Page, test } from '@playwright/test'

const password = 'Password123!'

async function login(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

async function logout(page: Page) {
  await page.getByRole('button', { name: 'Log out' }).click()
  await expect(page).toHaveURL(/\/login$/)
}

test.describe.serial('role-adaptive integrated workflows', () => {
  test('public student registration, login, authenticated session, and logout', async ({ page }) => {
    await page.goto('/register')
    await page.getByLabel('Full name').fill('Registered E2E Student')
    await page.getByLabel('University email').fill('registered.e2e@example.edu')
    await page.getByLabel(/Password/).fill(password)
    await page.getByRole('button', { name: 'Create student account' }).click()
    await expect(page).toHaveURL(/\/login$/)

    await login(page, 'registered.e2e@example.edu')
    await expect(page.getByRole('heading', { name: /Good .* Registered/ })).toBeVisible()
    await page.reload()
    await expect(page).toHaveURL(/\/dashboard$/)
    await logout(page)
  })

  test('student personal timetable, enrollments, clash reporting, notifications, and account', async ({ page }) => {
    await login(page, 'student.e2e@example.edu')
    await expect(page.getByRole('heading', { name: /Good .* E2E/ })).toBeVisible()

    await page.getByRole('link', { name: 'My Timetable' }).click()
    await expect(page.getByRole('heading', { name: 'My timetable' })).toBeVisible()
    await expect(page.getByText('Artificial Intelligence')).toBeVisible()

    await page.getByRole('link', { name: 'Enrollments' }).click()
    await expect(page.getByRole('heading', { name: 'Enrollments', exact: true })).toBeVisible()
    await expect(page.getByText('AI-301', { exact: true })).toBeVisible()

    await page.getByRole('link', { name: 'Clash Reports' }).click()
    await page.getByRole('button', { name: 'New report' }).click()
    const checkboxes = page.locator('.selectable-classes input[type="checkbox"]')
    await expect(checkboxes).toHaveCount(2)
    await checkboxes.nth(0).check()
    await checkboxes.nth(1).check()
    await page.getByLabel('Notes').fill('These two seeded classes overlap.')
    await page.getByRole('button', { name: 'Submit report' }).click()
    await expect(page.getByText('Clash report submitted.')).toBeVisible()
    await expect(page.getByText('AI-301 ↔ MTH-201').first()).toBeVisible()

    await page.getByRole('link', { name: 'Notifications', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Notifications & reminders' })).toBeVisible()
    await expect(page.getByText('Welcome to the E2E timetable')).toBeVisible()
    await page.getByRole('button', { name: 'Mark read' }).click()

    await page.getByRole('link', { name: 'Account', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Account' })).toBeVisible()
    await expect(page.getByText('student.e2e@example.edu')).toBeVisible()
    await logout(page)
  })

  test('faculty sees only assigned teaching data', async ({ page }) => {
    await login(page, 'faculty.e2e@example.edu')
    await expect(page.getByText('Faculty', { exact: true }).first()).toBeVisible()

    await page.getByRole('link', { name: 'Assignments' }).click()
    await expect(page.getByRole('heading', { name: 'My assignments' })).toBeVisible()
    await expect(page.getByText('AI-301', { exact: true })).toBeVisible()

    await page.getByRole('link', { name: 'My Timetable' }).click()
    await expect(page.getByRole('heading', { name: 'Teaching timetable' })).toBeVisible()
    await expect(page.getByText('Artificial Intelligence')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Optimizer' })).toHaveCount(0)
    await logout(page)
  })

  test('coordinator reviews clashes, student reports, safe time changes, and history', async ({ page }) => {
    await login(page, 'coordinator.e2e@example.edu')

    await page.getByRole('link', { name: 'Clash Management' }).click()
    await expect(page.getByRole('heading', { name: 'Clash management' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Detected structural clashes' })).toBeVisible()
    await expect(page.getByText('AI-301 ↔ MTH-201').first()).toBeVisible()

    await page.getByRole('link', { name: 'Student Reports' }).click()
    await page.locator('.case-row').first().click()
    await page.getByRole('button', { name: 'Update case' }).click()
    await page.getByLabel('Next status').selectOption('under_review')
    await page.getByLabel('Review note').fill('Coordinator review started.')
    await page.getByRole('button', { name: 'Save status' }).click()
    await expect(page.getByText('Clash report updated.')).toBeVisible()

    await page.getByRole('link', { name: 'Faculty Assignments' }).click()
    await expect(page.getByRole('heading', { name: 'Faculty assignments' })).toBeVisible()
    await page.getByLabel('Find faculty').fill('faculty.e2e')
    await expect(page.getByLabel('Faculty member')).toContainText('E2E Faculty')

    await page.getByRole('link', { name: 'Timetable', exact: true }).click()
    await page.getByRole('button', { name: 'List' }).click()
    const aiRow = page.getByRole('row').filter({ hasText: 'AI-301' })
    await aiRow.getByRole('button', { name: 'Change day and time' }).click()
    const timeDialog = page.getByRole('dialog', { name: /Change day and time/ })
    await timeDialog.getByRole('combobox').selectOption('Tuesday')
    await timeDialog.getByRole('button', { name: 'Save day and time' }).click()
    await expect(page.getByText('Timetable day and time updated safely.')).toBeVisible()

    await page.getByRole('link', { name: 'History' }).click()
    await expect(page.getByText('Manual Time Change')).toBeVisible()
    page.once('dialog', (dialog) => dialog.accept())
    await page.getByRole('button', { name: 'Undo', exact: true }).first().click()
    await expect(page.getByText('Timetable change undo completed.')).toBeVisible()

    await page.getByRole('link', { name: 'Optimizer' }).click()
    await expect(page.getByRole('heading', { name: 'Optimizer', exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Ranked global moves' })).toBeVisible()
    await logout(page)
  })

  test('admin can access privileged account and full operations views', async ({ page }) => {
    await login(page, 'admin.e2e@example.edu')
    await page.getByRole('link', { name: 'Users & Roles' }).click()
    await expect(page.getByRole('heading', { name: 'Users & roles' })).toBeVisible()
    await expect(page.getByText('student.e2e@example.edu')).toBeVisible()
    await page.getByRole('button', { name: 'Manage' }).first().click()
    await expect(page.getByRole('dialog', { name: /Manage/ })).toBeVisible()
    await page.getByRole('button', { name: 'Cancel' }).click()

    await page.getByRole('link', { name: 'Clash Management' }).click()
    await expect(page.getByRole('heading', { name: 'Clash management' })).toBeVisible()
    await logout(page)
  })
})
