import { expect, type Page, test } from '@playwright/test'

const password = 'Password123!'

async function login(
  page: Page,
  identifier: string,
  passwordValue = password,
  expectedPath = '/dashboard',
) {
  await page.goto('/login')
  await page.getByLabel('Email or registration number').fill(identifier)
  await page.getByLabel('Password').fill(passwordValue)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(new RegExp(`${expectedPath}$`))
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
    await page.getByRole('button', { name: 'Conflict clusters' }).click()
    await page.locator('.case-row').first().click()
    await expect(page.getByText('Verified affected', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Update case status' }).click()
    await page.getByLabel('Next status').selectOption('under_review')
    await page.getByLabel('Review note').fill('Coordinator review started.')
    await page.getByRole('button', { name: 'Save status' }).click()
    await expect(page.getByText('Clash report updated.')).toBeVisible()

    const applyButton = page.getByRole('button', { name: /Review & apply/ }).first()
    await expect(applyButton).toBeEnabled()
    await applyButton.click()
    const resolutionDialog = page.getByRole('dialog', { name: /Apply resolution for case/ })
    const conditional = resolutionDialog.getByRole('checkbox')
    if (await conditional.count()) await conditional.check()
    await resolutionDialog.getByLabel('Resolution note').fill('Approved deterministic move after impact review.')
    await resolutionDialog.getByRole('button', { name: 'Apply after live revalidation' }).click()
    await expect(page.getByText(/Resolution applied\./)).toBeVisible()
    await expect(page.getByText(/Linked timetable resolution/)).toBeVisible()

    await page.getByRole('button', { name: 'Undo resolution' }).click()
    await expect(page.getByText(/Resolution undone/)).toBeVisible()
    await expect(page.getByRole('button', { name: 'Safe redo' })).toBeVisible()
    await page.getByRole('button', { name: 'Safe redo' }).click()
    await expect(page.getByText(/Resolution safely redone/)).toBeVisible()

    await page.getByRole('link', { name: 'Quality & Analytics' }).click()
    await expect(page.getByRole('heading', { name: 'Resolver quality & analytics' })).toBeVisible()
    await expect(page.getByText('Confirmed conflicts', { exact: true })).toBeVisible()

    await page.getByRole('link', { name: 'Faculty Assignments' }).click()
    await expect(page.getByRole('heading', { name: 'Faculty assignments', exact: true })).toBeVisible()
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

  test('student receives coordinator schedule resolution updates', async ({ page }) => {
    await login(page, 'student.e2e@example.edu')

    await page.getByRole('link', { name: 'Notifications', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Notifications & reminders' })).toBeVisible()
    await expect(page.getByText(/Schedule changed for/).first()).toBeVisible()

    await page.getByRole('link', { name: 'My Timetable' }).click()
    await expect(page.getByRole('heading', { name: 'My timetable' })).toBeVisible()
    await expect(page.getByText('Artificial Intelligence')).toBeVisible()
    await expect(page.getByText('Discrete Mathematics')).toBeVisible()

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
test('coordinator provisions a registration-login student through first-login onboarding', async ({ page }) => {
  const registrationNumber = 'E2E-NEW-001'
  const permanentPassword = 'Provisioned123!'

  await login(page, 'coordinator.e2e@example.edu')
  await page.getByRole('link', { name: 'Students' }).click()
  await expect(page.getByRole('heading', { name: 'Students' })).toBeVisible()

  await page.getByRole('button', { name: 'Provision student' }).click()
  const provisionDialog = page.getByRole('dialog', {
    name: 'Provision institutional student',
  })
  await provisionDialog.getByLabel('Registration number').fill(registrationNumber)
  await provisionDialog.getByLabel('Full name').fill('Registration Login Student')
  await provisionDialog.getByLabel('Department').fill('Computing')
  await provisionDialog.getByLabel('Program').fill('BS Artificial Intelligence')
  await provisionDialog.getByLabel('Batch').fill('2026')
  await provisionDialog.getByLabel('Current semester').fill('1')
  await provisionDialog.getByLabel('Section').fill('B')
  await provisionDialog.getByRole('button', { name: 'Provision student' }).click()

  const credentialDialog = page.getByRole('dialog', {
    name: 'Temporary student credential',
  })
  const temporaryPassword = (
    await credentialDialog.getByTestId('temporary-password').textContent()
  )?.trim()
  if (!temporaryPassword) {
    throw new Error('Provisioned student temporary password was not shown.')
  }
  await credentialDialog.getByRole('button', { name: 'Done' }).click()
  await logout(page)

  await login(page, registrationNumber, temporaryPassword, '/account')
  await expect(page).toHaveURL(/\/account$/)
  await expect(
    page.getByText('First sign-in: change your temporary password'),
  ).toBeVisible()

  await page.getByLabel('Current password').fill(temporaryPassword)
  await page.getByLabel('New password').fill(permanentPassword)
  await page.getByRole('button', { name: 'Change password' }).click()
  await expect(page).toHaveURL(/\/login$/, { timeout: 5_000 })

  await login(page, registrationNumber, permanentPassword, '/account')
  await expect(page).toHaveURL(/\/account$/)
  await expect(
    page.getByRole('heading', { name: 'Finish student onboarding' }),
  ).toBeVisible()
  await page.getByLabel('Preferred name').fill('E2E New Student')
  await page.getByRole('button', { name: 'Complete onboarding' }).click()
  await expect(page.getByText('Student onboarding completed.')).toBeVisible()

  await page.getByRole('link', { name: 'Dashboard' }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
  await logout(page)
})

test('coordinator mobile navigation exposes operational workspaces', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await login(page, 'coordinator.e2e@example.edu')
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible()
  await page.getByRole('button', { name: 'Open navigation' }).click()
  await expect(page.getByRole('link', { name: 'Students' })).toBeVisible()
  await page.getByRole('link', { name: 'Students' }).click()
  await expect(page.getByRole('heading', { name: 'Students' })).toBeVisible()
})

  test('coordinator switches academic terms without leaking archived student data', async ({ page }) => {
    await login(page, 'coordinator.e2e@example.edu')

    await page.getByRole('link', { name: 'Academic Terms' }).click()
    await expect(page.getByRole('heading', { name: 'Academic terms' })).toBeVisible()

    await page.getByLabel('Term code').fill('SPRING-2027')
    await page.getByLabel('Term name').fill('Spring 2027')
    await page.getByLabel('Starts on').fill('2027-01-11')
    await page.getByLabel('Ends on').fill('2027-05-28')
    await page.getByRole('button', { name: 'Create planning term' }).click()
    await expect(page.getByText('Planning academic term created.')).toBeVisible()

    const springTerm = page.locator('.enrollment-list article').filter({ hasText: 'Spring 2027' })
    await expect(springTerm.getByText('SPRING-2027 - planning')).toBeVisible()

    await page.getByRole('link', { name: 'Scheduling', exact: true }).click()
    await expect(
      page.getByRole('heading', { name: 'Institutional scheduling' }),
    ).toBeVisible()
    await page.getByLabel('Academic term').selectOption({
      label: 'Spring 2027 - planning',
    })

    await page.getByLabel('Course code').fill('DS-220')
    await page.getByLabel('Course name').fill('Data Structures II')
    await page.getByLabel('Semester').selectOption('2')
    await page.getByLabel('Section').fill('B')
    await page.getByLabel('Class type').selectOption('lecture')
    await page.getByLabel('Duration minutes').fill('60')
    await page.getByLabel('Room/location').fill('R-401')
    await page.getByRole('button', { name: 'Add offering' }).click()
    await expect(page.getByText('Course offering created.')).toBeVisible()

    await page.getByLabel('Faculty member').selectOption({
      label: 'E2E Faculty · faculty.e2e@example.edu',
    })
    await page.getByLabel('Teaching designation').selectOption('lecturer')
    await page.getByRole('button', { name: 'Save designation' }).click()
    await expect(
      page.getByText('Faculty teaching designation saved.'),
    ).toBeVisible()

    await page.getByLabel('Availability day').selectOption('Tuesday')
    await page.getByLabel('Available from').fill('08:00')
    await page.getByLabel('Available until').fill('12:00')
    await page.getByRole('button', { name: 'Add availability' }).click()
    await expect(page.getByText('Faculty availability added.')).toBeVisible()

    await page.getByLabel('Availability day').selectOption('Thursday')
    await page.getByRole('button', { name: 'Add availability' }).click()
    await expect(page.getByText('Faculty availability added.')).toBeVisible()

    await page.getByRole('link', { name: 'Faculty allocations' }).click()
    await expect(
      page.getByRole('heading', { name: 'Faculty assignments', exact: true }),
    ).toBeVisible()
    await page.getByLabel('Academic term').selectOption({
      label: 'Spring 2027 - planning',
    })
    await page.getByLabel('Faculty member').selectOption({
      label: 'E2E Faculty · faculty.e2e@example.edu',
    })
    await page.getByLabel('Course offering').selectOption({
      label: 'DS-220 · Semester 2 · Section B',
    })
    await page.getByRole('button', { name: 'Add assignment' }).click()
    await expect(page.getByText('Faculty assignment created.')).toBeVisible()

    await page.getByRole('link', { name: 'Scheduling', exact: true }).click()
    await page.getByLabel('Academic term').selectOption({
      label: 'Spring 2027 - planning',
    })
    await page
      .getByRole('button', { name: 'Preview timetable generation' })
      .click()
    await expect(
      page.getByText('Timetable generation preview refreshed.'),
    ).toBeVisible()
    await expect(page.getByText('READY', { exact: true }).first()).toBeVisible()
    await expect(page.getByText('DS-220', { exact: true }).first()).toBeVisible()

    page.once('dialog', (dialog) => dialog.accept())
    await page.getByRole('button', { name: 'Apply verified preview' }).click()
    await expect(
      page.getByText('Timetable generation applied successfully.'),
    ).toBeVisible()

    await page.getByRole('link', { name: 'Quality', exact: true }).click()
    await expect(
      page.getByRole('heading', { name: 'Resolver quality & analytics' }),
    ).toBeVisible()
    await page.getByLabel('Academic term').selectOption({
      label: 'Spring 2027 - planning',
    })
    await expect(page.getByText('SPRING-2027 - planning')).toBeVisible()
    await expect(
      page.getByRole('link', { name: 'Open scheduling' }),
    ).toBeVisible()

    await page.getByRole('link', { name: 'Timetable', exact: true }).click()
    await expect(
      page.getByRole('heading', { name: 'Timetable management' }),
    ).toBeVisible()

    const timetableTermSelect = page.getByLabel('Academic term')
    const planningTermId = await timetableTermSelect
      .locator('option', { hasText: 'Spring 2027 - planning' })
      .getAttribute('value')
    if (!planningTermId) {
      throw new Error('Planning term option is missing a value.')
    }

    await timetableTermSelect.selectOption(planningTermId)
    await expect(timetableTermSelect).toHaveValue(planningTermId)

    await page.getByRole('button', { name: 'List' }).click()
    const generatedRows = page.getByRole('row').filter({ hasText: 'DS-220' })
    await expect(generatedRows).toHaveCount(2, { timeout: 20_000 })
    await expect(
      generatedRows.first().getByText('Generated', { exact: true }),
    ).toBeVisible()
    await expect(
      generatedRows.first().getByText('Data Structures II'),
    ).toBeVisible()

    await page.getByRole('button', { name: 'Week' }).click()

    await page.getByRole('link', { name: 'Timetable', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Timetable management' })).toBeVisible()
    await page.getByLabel('Academic term').selectOption({ label: 'Spring 2027 - planning' })
    await expect(page.getByText('Artificial Intelligence')).toHaveCount(0)
    await page.getByRole('button', { name: 'New entry' }).click()
    const planningEntryDialog = page.getByRole('dialog', { name: 'Create timetable entry' })
    await planningEntryDialog.getByLabel('Course code').fill('NLP-401')
    await planningEntryDialog.getByLabel('Course name').fill('Natural Language Processing')
    await planningEntryDialog.getByLabel('Section').fill('A')
    await planningEntryDialog.getByLabel('Semester').fill('Spring 2027')
    await planningEntryDialog.getByLabel('Faculty').fill('E2E Faculty')
    await planningEntryDialog.getByLabel('Room').fill('LAB-2')
    await planningEntryDialog.getByRole('button', { name: 'Create entry' }).click()
    await expect(page.getByText('Timetable entry created.')).toBeVisible()
    await expect(page.getByText('Natural Language Processing')).toBeVisible()

    await page.getByRole('button', { name: 'New entry' }).click()
    const planningClashDialog = page.getByRole('dialog', { name: 'Create timetable entry' })
    await planningClashDialog.getByLabel('Course code').fill('ML-402')
    await planningClashDialog.getByLabel('Course name').fill('Machine Learning Systems')
    await planningClashDialog.getByLabel('Section').fill('A')
    await planningClashDialog.getByLabel('Semester').fill('Spring 2027')
    await planningClashDialog.getByLabel('Faculty').fill('Dr Planning')
    await planningClashDialog.getByLabel('Room').fill('LAB-2')
    await planningClashDialog.getByRole('button', { name: 'Create entry' }).click()
    await expect(page.getByText('Timetable entry created.')).toBeVisible()
    await expect(page.getByText('Machine Learning Systems')).toBeVisible()

    await page.getByRole('link', { name: 'Clash Management' }).click()
    await expect(page.getByRole('heading', { name: 'Clash management' })).toBeVisible()
    await page.getByLabel('Academic term').selectOption({ label: 'Spring 2027 - planning' })
    await expect(page.getByText('SPRING-2027 - planning - analysis only')).toBeVisible()
    await expect(page.getByText(/NLP-401 ↔ ML-402|ML-402 ↔ NLP-401/).first()).toBeVisible()
    await expect(page.getByRole('button', { name: 'Apply fix' }).first()).toBeDisabled()

    await page.getByRole('link', { name: 'Optimizer' }).click()
    await expect(page.getByRole('heading', { name: 'Optimizer', exact: true })).toBeVisible()
    await page.getByLabel('Academic term').selectOption({ label: 'Spring 2027 - planning' })
    await expect(page.getByText('SPRING-2027 - planning - analysis only')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Apply best move' })).toBeDisabled()

    await page.getByRole('link', { name: 'Academic Terms' }).click()
    await expect(page.getByRole('heading', { name: 'Academic terms' })).toBeVisible()

    page.once('dialog', (dialog) => dialog.accept())
    await springTerm.getByRole('button', { name: 'Activate' }).click()
    await expect(page.getByText(/Archive the current active term/)).toBeVisible()

    const activeTerm = page.locator('.enrollment-list article').filter({ hasText: 'active' }).first()
    page.once('dialog', (dialog) => dialog.accept())
    await activeTerm.getByRole('button', { name: 'Archive' }).click()
    await expect(page.getByText('Academic term archived.')).toBeVisible()

    page.once('dialog', (dialog) => dialog.accept())
    await springTerm.getByRole('button', { name: 'Activate' }).click()
    await expect(page.getByText('Academic term activated.')).toBeVisible()
    await expect(springTerm.getByText('SPRING-2027 - active')).toBeVisible()

    await page.getByRole('link', { name: 'Timetable', exact: true }).click()
    await expect(page.getByText('Natural Language Processing')).toBeVisible()

    await page.getByLabel('Academic term').selectOption({ label: 'Legacy Imported Term - archived' })
    await expect(page.getByText('Artificial Intelligence')).toBeVisible()
    await expect(page.getByText('Natural Language Processing')).toHaveCount(0)
    await expect(page.getByText('LEGACY-IMPORTED - archived - read-only')).toBeVisible()
    await expect(page.getByRole('button', { name: 'New entry' })).toHaveCount(0)
    await expect(page.getByText('Import CSV/XLSX')).toHaveCount(0)
    await page.getByRole('button', { name: 'List' }).click()
    await expect(page.getByRole('button', { name: 'Change room' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Change day and time' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Delete entry' })).toHaveCount(0)

    await page.getByLabel('Academic term').selectOption({ label: 'Spring 2027 - active' })
    await expect(page.getByText('Natural Language Processing')).toBeVisible()

    await logout(page)

    await login(page, 'student.e2e@example.edu')
    await page.getByRole('link', { name: 'My Timetable' }).click()
    await expect(page.getByText('Artificial Intelligence')).toHaveCount(0)

    await page.getByRole('link', { name: 'Enrollments' }).click()
    await expect(page.getByText('AI-301', { exact: true })).toHaveCount(0)

    await logout(page)
  })

})
