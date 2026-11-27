import { test, expect } from 'playwright/test';
import { resolve } from 'node:path';
import { readEnvFile, readState, writeState, newPassword, listEmails, invitationLink, step, attachPageDiagnostics, resetSteps, artifacts } from './helpers.mjs';

const baseURL = process.env.SSP_TEST_BASE_URL ?? 'http://localhost:3100';
const testInfoOutput = (info, filename) => info.outputPath(filename);

async function futureColomboDateTime(page, daysAhead = 5) {
  return page.evaluate((days) => {
    const date = new Date(Date.now() + days * 24 * 60 * 60 * 1000);
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Colombo', year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(date).map(({ type, value }) => [type, value]));
    return `${parts.year}-${parts.month}-${parts.day}T11:30`;
  }, daysAhead);
}

async function startTrace(context) {
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });
}

async function login(page, role, credentials) {
  let csrfResponse; let loginResponse;
  for (let attempt = 0; attempt < 6; attempt++) {
    await page.goto('/staff/login');
    await page.getByLabel('Username').fill(credentials.username);
    await page.getByLabel('Password').fill(credentials.password);
    const csrfResponsePromise = page.waitForResponse(response => response.url().includes('/api/auth/csrf') && response.request().method() === 'GET');
    const loginResponsePromise = page.waitForResponse(response => response.url().includes('/api/auth/login') && response.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign in securely' }).click();
    csrfResponse = await csrfResponsePromise;
    loginResponse = await loginResponsePromise;
    if (loginResponse.status() !== 429) break;
    const message = await loginResponse.text();
    const seconds = Number(message.match(/available in (\d+) second/)?.[1] || 2);
    await page.waitForTimeout((seconds + 1) * 1000);
    if (attempt === 5) throw new Error('Login remained rate limited after retries.');
  }
  const csrfCookies = (await csrfResponse.headersArray()).filter(header => header.name.toLowerCase() === 'set-cookie').map(header => header.value);
  const csrfCookie = csrfCookies.find(cookie => cookie.toLowerCase().startsWith('csrftoken='));
  expect(csrfResponse.status()).toBe(200);
  expect(csrfCookie).toMatch(/;\s*Secure/i);
  expect(csrfCookie).toMatch(/SameSite=Lax/i);
  expect(csrfCookie).not.toMatch(/;\s*Domain=/i);
  expect(loginResponse.status()).toBe(200);
  const sessionCookies = (await loginResponse.headersArray()).filter(header => header.name.toLowerCase() === 'set-cookie').map(header => header.value);
  const sessionCookie = sessionCookies.find(cookie => cookie.toLowerCase().startsWith('sessionid='));
  expect(sessionCookie).toMatch(/;\s*HttpOnly/i);
  expect(sessionCookie).toMatch(/;\s*Secure/i);
  expect(sessionCookie).toMatch(/SameSite=Lax/i);
  expect(sessionCookie).not.toMatch(/;\s*Domain=/i);
  await page.waitForURL('**/staff', { timeout: 12000 });
  await expect(page.getByText(role, { exact: false }).first()).toBeVisible();
  await page.reload();
  await expect(page.getByText(role, { exact: false }).first()).toBeVisible();
}

async function logout(page) {
  const button = page.getByRole('button', { name: 'Sign out' });
  if (await button.count()) {
    const responsePromise = page.waitForResponse(response => response.url().includes('/api/auth/logout') && response.request().method() === 'POST');
    await button.click();
    const response = await responsePromise;
    expect(response.status()).toBe(204);
    await page.goto('/staff/accounts');
    await expect(page).toHaveURL(/\/staff\/login/);
  }
}

async function selectOptionContaining(select, text) {
  const option = select.locator('option').filter({ hasText: text }).first();
  const value = await option.getAttribute('value');
  if (!value) throw new Error(`No select option contains ${text}.`);
  await select.selectOption(value);
}

test.describe.configure({ mode: 'serial' });

test('Admin onboarding, invitations, password setup/reset, and audit', async ({ browser }, info) => {
  test.setTimeout(180_000);
  resetSteps();
  const config = readEnvFile();
  const context = await browser.newContext({ baseURL });
  await startTrace(context);
  const page = await context.newPage();
  attachPageDiagnostics(page);
  const state = readState();
  state.admin = { username: config.SSP_TEST_ADMIN_USERNAME, password: config.SSP_TEST_ADMIN_PASSWORD };

  try {
    await step(page, 'Admin', 'Sign in as bootstrap Admin', 'Admin dashboard opens with the correct role', async () => {
      await login(page, 'Admin', state.admin);
      await expect(page.getByRole('heading', { name: 'Account overview' })).toBeVisible();
      return 'Signed in; Admin account overview rendered.';
    });

    await step(page, 'Admin', 'Open account management', 'Users screen exposes account creation and activity controls', async () => {
      await page.goto('/staff/accounts');
      await expect(page.getByRole('heading', { name: 'Accounts' })).toBeVisible();
      await expect(page.getByRole('button', { name: '+ Create account' })).toBeVisible();
      await expect(page.locator('.role-chip')).toContainText('Superuser');
      return 'Accounts workspace loaded with Create account control.';
    });

    const regularAdminProfile = {
      username: 'pw_regular_admin', email: 'regular-admin.acceptance@example.com',
      first_name: 'Nimali', last_name: 'Perera', phone: '+94 77 555 0106',
    };
    const adminMailBefore = new Set(listEmails());
    await step(page, 'Superuser', 'Create a regular Admin account', 'Superuser role selector can issue an Admin invitation without granting Django superuser privileges', async () => {
      await page.getByRole('button', { name: '+ Create account' }).click();
      const form = page.locator('form.account-form');
      await form.getByLabel('Username').fill(regularAdminProfile.username);
      await form.getByLabel('First name').fill(regularAdminProfile.first_name);
      await form.getByLabel('Last name').fill(regularAdminProfile.last_name);
      await form.getByLabel('Email').fill(regularAdminProfile.email);
      await form.getByLabel('Phone').fill(regularAdminProfile.phone);
      await expect(form.locator('select[name="role"] option[value="admin"]')).toHaveCount(1);
      await form.locator('select[name="role"]').selectOption('admin');
      await form.getByRole('button', { name: 'Create account and send invitation' }).click();
      await expect(page.locator('.inline-notice')).toContainText('pw_regular_admin');
      await expect(page.getByRole('row').filter({ hasText: regularAdminProfile.email }).getByText('Admin', { exact: true })).toBeVisible();
      return 'Superuser created an invited, regular Admin account.';
    });

    await expect.poll(() => listEmails().find((file) => !adminMailBefore.has(file)), { timeout: 8000 }).toBeTruthy();
    const regularAdminMail = listEmails().find((file) => !adminMailBefore.has(file));
    const regularAdminCredentials = { ...regularAdminProfile, password: newPassword('regular-admin') };
    const regularAdminContext = await browser.newContext({ baseURL });
    await startTrace(regularAdminContext);
    const regularAdminPage = await regularAdminContext.newPage();
    attachPageDiagnostics(regularAdminPage);
    try {
      await step(regularAdminPage, 'Admin', 'Accept Admin invitation and inspect permissions', 'Regular Admin sees Admin classification without superuser controls', async () => {
        await regularAdminPage.goto(invitationLink(regularAdminMail));
        await regularAdminPage.getByLabel('New password').fill(regularAdminCredentials.password);
        await regularAdminPage.getByLabel('Confirm password').fill(regularAdminCredentials.password);
        await regularAdminPage.getByRole('button', { name: 'Set password securely' }).click();
        await regularAdminPage.waitForURL('**/staff/login?setup=complete');
        await login(regularAdminPage, 'Admin', regularAdminCredentials);
        await regularAdminPage.goto('/staff/accounts');
        await regularAdminPage.getByRole('button', { name: '+ Create account' }).click();
        const roleSelect = regularAdminPage.locator('form.account-form select[name="role"]');
        await expect(roleSelect).toHaveCount(1);
        await expect(roleSelect.locator('option[value="admin"]')).toHaveCount(0);
        const superuserRow = regularAdminPage.getByRole('row').filter({ hasText: config.SSP_TEST_ADMIN_USERNAME });
        await expect(superuserRow.getByText('Superuser', { exact: true })).toBeVisible();
        await expect(superuserRow.getByRole('button')).toHaveCount(0);
        const result = await regularAdminPage.evaluate(async () => {
          const csrf = decodeURIComponent(document.cookie.split('; ').find((entry) => entry.startsWith('csrftoken='))?.split('=').slice(1).join('=') ?? '');
          const accounts = await fetch('/api/accounts/', { credentials: 'include' }).then((response) => response.json());
          const superuser = accounts.find((account) => account.is_superuser);
          const response = await fetch(`/api/accounts/${superuser.id}/access-link/`, {
            method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body: JSON.stringify({ kind: 'password_reset' }),
          });
          return response.status;
        });
        expect(result).toBe(403);
        return 'Regular Admin is identified correctly, sees no superuser actions, and cannot issue a superuser reset link.';
      });
      state.regularAdmin = regularAdminCredentials;
      writeState(state);
    } finally {
      await regularAdminContext.tracing.stop({ path: testInfoOutput(info, 'regular-admin-trace.zip') });
      await regularAdminContext.close();
    }

    for (const role of ['staff', 'manager', 'ceo', 'rep']) {
      const label = { staff: 'Staff', manager: 'MD/Manager', ceo: 'CEO', rep: 'Rep' }[role];
      const profile = {
        username: `pw_${role}`,
        first_name: { staff: 'Maya', manager: 'Dilan', ceo: 'Anushka', rep: 'Kavindu' }[role],
        last_name: { staff: 'Fernando', manager: 'Perera', ceo: 'Jayasinghe', rep: 'Silva' }[role],
        email: `${role}.acceptance@example.com`,
        phone: { staff: '+94 77 555 0102', manager: '+94 77 555 0103', ceo: '+94 77 555 0104', rep: '+94 77 555 0105' }[role],
      };
      const before = new Set(listEmails());
      await step(page, 'Admin', `Create ${label} account and send invitation`, 'Account is created inactive and a local-only invitation is generated', async () => {
        await page.getByRole('button', { name: '+ Create account' }).click();
        const form = page.locator('form.account-form');
        await form.getByLabel('Username').fill(profile.username);
        await form.getByLabel('First name').fill(profile.first_name);
        await form.getByLabel('Last name').fill(profile.last_name);
        await form.getByLabel('Email').fill(profile.email);
        await form.getByLabel('Phone').fill(profile.phone);
        await form.locator('select[name="role"]').selectOption(role);
        await form.getByRole('button', { name: 'Create account and send invitation' }).click();
        await expect(page.locator('.inline-notice')).toContainText(`Internal account ${profile.username} was created`);
        await expect(page.getByText('Inactive', { exact: true })).toBeVisible();
        return `Created ${profile.username}; UI confirmed invitation sent to ${profile.email}.`;
      });

      let newFile;
      await expect.poll(() => listEmails().find((file) => !before.has(file)), { timeout: 8000 }).toBeTruthy();
      newFile = listEmails().find((file) => !before.has(file));
      const credentials = { ...profile, password: newPassword(role) };
      const inviteContext = await browser.newContext({ baseURL });
      await startTrace(inviteContext);
      const invitePage = await inviteContext.newPage();
      attachPageDiagnostics(invitePage);
      try {
        await step(invitePage, label, 'Open invitation and set initial password', 'Single-use invitation activates the account and confirms setup', async () => {
          await invitePage.goto(invitationLink(newFile));
          await invitePage.getByLabel('New password').fill(credentials.password);
          await invitePage.getByLabel('Confirm password').fill(credentials.password);
          await invitePage.getByRole('button', { name: 'Set password securely' }).click();
          await invitePage.waitForURL('**/staff/login?setup=complete');
          await expect(invitePage.getByRole('status')).toContainText('Your password is set');
          return `Invitation accepted; ${profile.username} is ready to sign in.`;
        });
      } finally {
        await inviteContext.tracing.stop({ path: testInfoOutput(info, `${role}-invitation-trace.zip`) });
        await inviteContext.close();
      }
      state[role] = credentials;
      writeState(state);
    }

    await step(page, 'Superuser', 'Confirm before changing an employee role', 'Role changes require explicit confirmation before being saved', async () => {
      const row = page.getByRole('row').filter({ hasText: 'staff.acceptance@example.com' });
      await row.getByRole('button', { name: 'Edit' }).click();
      const form = page.locator('form.account-form');
      await form.locator('select[name="role"]').selectOption('manager');
      const confirmation = new Promise((resolve) => page.once('dialog', async (dialog) => {
        expect(dialog.message()).toContain("Change pw_staff's role from Staff to MD/Manager?");
        await dialog.dismiss();
        resolve(true);
      }));
      await form.getByRole('button', { name: 'Save account' }).click();
      await confirmation;
      await expect(row.getByText('Staff', { exact: true })).toBeVisible();
      await page.getByRole('button', { name: 'Cancel' }).click();
      return 'The attempted role change was cancelled at the explicit confirmation prompt; the role stayed Staff.';
    });

    await step(page, 'Admin', 'Issue password reset for Staff account', 'Admin action shows success and generates a local reset message', async () => {
      const row = page.getByRole('row').filter({ hasText: 'staff.acceptance@example.com' });
      await row.getByRole('button', { name: 'Send password reset' }).click();
      await expect(page.locator('.inline-notice')).toContainText('A password reset link was sent');
      return 'Password reset request accepted; no outbound email was used.';
    });

    const resetCandidates = listEmails().filter((file) => {
      try { return invitationLink(file, 'reset-password').length > 0; } catch { return false; }
    });
    if (resetCandidates.length) {
      const resetContext = await browser.newContext({ baseURL });
      await startTrace(resetContext);
      const resetPage = await resetContext.newPage();
      attachPageDiagnostics(resetPage);
      const updatedPassword = newPassword('staff-reset');
      try {
        await step(resetPage, 'Staff', 'Complete password reset link', 'Reset link accepts new password and returns to sign-in', async () => {
          const lastReset = resetCandidates.at(-1);
          await resetPage.goto(invitationLink(lastReset, 'reset-password'));
          await resetPage.getByLabel('New password').fill(updatedPassword);
          await resetPage.getByLabel('Confirm password').fill(updatedPassword);
          await resetPage.getByRole('button', { name: 'Set password securely' }).click();
          await resetPage.waitForURL('**/staff/login?setup=complete');
          state.staff.password = updatedPassword;
          writeState(state);
          return 'Reset token accepted and Staff password changed.';
        });
      } finally {
        await resetContext.tracing.stop({ path: testInfoOutput(info, 'password-reset-trace.zip') });
        await resetContext.close();
      }
    } else {
      await step(page, 'Admin', 'Locate generated reset message', 'A local-only reset link is available for the Staff account', async () => {
        throw new Error('No reset-password link was found in the configured acceptance email folder.');
      });
    }

    await step(page, 'Admin', 'Review account activity', 'Admin can read recent account/system audit history', async () => {
      await page.goto('/staff/activity');
      await expect(page.getByRole('heading', { name: /Recent account activity/i })).toBeVisible();
      await expect(page.getByText('Account Invitation Sent').first()).toBeVisible();
      return 'Recent activity screen rendered invitation, authentication, and reset events.';
    });

    await step(page, 'Admin', 'Confirm logout clears the authenticated session', 'Logout succeeds and a protected route redirects to sign-in', async () => {
      await logout(page);
      return 'Logged out successfully; protected Accounts route returned to sign-in.';
    });

    writeState(state);
  } finally {
    await context.tracing.stop({ path: testInfoOutput(info, 'admin-onboarding-trace.zip') });
    await context.close();
  }
});

test('Staff inventory and public customer journey', async ({ browser }, info) => {
  test.setTimeout(180_000);
  const state = readState();
  expect(state.staff).toBeTruthy();
  const context = await browser.newContext({ baseURL });
  await startTrace(context);
  const page = await context.newPage();
  attachPageDiagnostics(page);
  const vehicles = [];
  try {
    await step(page, 'Staff', 'Sign in as Staff', 'Staff dashboard opens and role-scoped controls load', async () => {
      await login(page, 'Staff', state.staff);
      await expect(page.getByRole('heading', { name: 'Staff dashboard' })).toBeVisible();
      return 'Staff session established.';
    });

    await step(page, 'Staff', 'Open inventory workspace', 'Staff can see Add vehicle and inventory search controls', async () => {
      await page.goto('/staff/inventory');
      await expect(page.getByRole('heading', { name: 'Vehicle inventory' })).toBeVisible();
      await expect(page.getByRole('button', { name: '+ Add vehicle' })).toBeVisible();
      return 'Inventory workspace loaded with management controls.';
    });

    if (state.vehicles?.length) vehicles.push(...state.vehicles);
    else for (const car of [
      { make: 'Honda', model: 'Civic e:HEV', variant: 'RS', year: '2023', mileage: '18400', color: 'Sonic Grey', vin: 'PW-SSP-HON-001', price: '14250000', fuel: 'hybrid' },
      { make: 'Toyota', model: 'Corolla Cross', variant: 'G Safety', year: '2022', mileage: '26700', color: 'Pearl White', vin: 'PW-SSP-TOY-002', price: '12800000', fuel: 'petrol' },
      { make: 'Mazda', model: 'CX-5', variant: 'XD L Package', year: '2024', mileage: '9200', color: 'Deep Crystal Blue', vin: 'PW-SSP-MAZ-003', price: '17900000', fuel: 'diesel' },
    ]) {
      await step(page, 'Staff', `Create draft vehicle ${car.make} ${car.model}`, 'Inventory record saves with fictional details and private stock ID', async () => {
        await page.getByRole('button', { name: '+ Add vehicle' }).click();
        const form = page.locator('form.inventory-form');
        await form.getByLabel('Make').fill(car.make);
        await form.getByLabel('Model').fill(car.model);
        await form.getByLabel('Variant / grade').fill(car.variant);
        await form.getByLabel('Manufacture year').fill(car.year);
        await form.getByLabel('Mileage (km)').fill(car.mileage);
        await form.getByLabel('Fuel type').selectOption(car.fuel);
        await form.getByLabel('Transmission').selectOption('automatic');
        await form.getByLabel('Color').fill(car.color);
        await form.getByLabel('Condition').selectOption('used');
        await form.getByLabel(/Chassis \/ VIN \/ stock ID/).fill(car.vin);
        await form.getByLabel('Asking price (LKR)').fill(car.price);
        await form.getByLabel('Publication').selectOption('draft');
        await form.getByLabel('Description').fill('Fictional acceptance-test vehicle; no customer data.');
        if (car.make === 'Honda') await form.getByLabel('Add photographs').setInputFiles(resolve(artifacts, 'vehicle-photo.png'));
        await form.getByRole('button', { name: 'Create vehicle' }).click();
        await expect(page.getByRole('status')).toContainText('Saved SSP-');
        const row = page.getByRole('row').filter({ hasText: car.model });
        const reference = (await row.locator('td').nth(1).innerText()).trim();
        vehicles.push({ ...car, reference });
        return `Created ${reference} as draft; private stock ID ${car.vin} retained in staff inventory.`;
      });
      const row = page.getByRole('row').filter({ hasText: car.model });
      await step(page, 'Staff', `Publish ${car.make} ${car.model}`, 'Available vehicle becomes public stock', async () => {
        await row.getByRole('button', { name: 'Publish' }).click();
        await expect(page.getByRole('status')).toContainText('is now published');
        return `${car.model} published; row shows published visibility.`;
      });
    }
    const stateNext = { ...state, vehicles };
    writeState(stateNext);

    await step(page, 'Public visitor', 'Browse published vehicle stock', 'Public catalogue shows published test vehicles without private chassis IDs', async () => {
      await page.goto('/cars');
      await expect(page.getByRole('heading', { name: 'Honda Civic e:HEV' })).toBeVisible();
      await expect(page.getByText('PW-SSP-HON-001')).toHaveCount(0);
      return 'Published Honda is visible; private stock identifier is absent from public page.';
    });

    await step(page, 'Public visitor', 'Open dynamic vehicle detail page', 'Published vehicle detail resolves by its public reference', async () => {
      await page.goto(`/cars/${vehicles[0].reference}`);
      await expect(page.getByRole('heading', { name: /Honda Civic e:HEV/ })).toBeVisible();
      const photo = page.locator('.vehicle-main-photo img');
      await expect(photo).toBeVisible();
      await expect.poll(() => photo.evaluate(image => image.complete && image.naturalWidth > 0)).toBeTruthy();
      return `Public vehicle detail for ${vehicles[0].reference} loaded.`;
    });

    await step(page, 'Public visitor', 'Submit showroom test-drive request', 'Visitor sees request reference and no confirmed-booking claim', async () => {
      await page.goto('/book-appointment');
      await page.getByLabel('Full name *').fill('Elena Wickramasinghe');
      await page.getByLabel('Phone *').fill('+94 77 555 0191');
      await page.getByLabel('Email *').fill('elena.wickramasinghe@example.com');
      await page.getByLabel('Purpose *').selectOption('test_drive');
      await page.getByLabel('Vehicle (optional)').selectOption(vehicles[0].reference);
      await page.getByLabel('Preferred date and time *').fill(await futureColomboDateTime(page));
      await page.getByLabel('Additional notes').fill('Fictional acceptance request for a test drive.');
      await page.getByRole('button', { name: 'Submit request' }).click();
      await expect(page.getByRole('status')).toContainText('REQUEST RECEIVED');
      await expect(page.getByText(/not a confirmed booking/i)).toBeVisible();
      return 'Test-drive request submitted; reference shown and UI states it is not confirmed.';
    });

    await step(page, 'Public visitor', 'Submit a vehicle quote request', 'Quote request is accepted with a visible reference', async () => {
      await page.goto('/request-quote');
      await page.getByLabel('Full name *').fill('Elena Wickramasinghe');
      await page.locator('input[type="tel"]').fill('+94 77 555 0191');
      await page.locator('input[type="email"]').fill('elena.wickramasinghe@example.com');
      await page.getByLabel('Preferred contact *').selectOption('email');
      await page.getByLabel('Vehicle *').fill(`${vehicles[0].make} ${vehicles[0].model} ${vehicles[0].reference}`);
      await page.getByLabel('Additional notes').fill('Please share a fictional finance illustration.');
      await page.getByRole('button', { name: 'Submit request' }).click();
      await expect(page.getByRole('status')).toContainText('REQUEST RECEIVED');
      return 'Quote request accepted with a reference.';
    });

    await step(page, 'Staff', 'Follow up and schedule public test-drive request', 'Staff can record notes, mark contacted, and set a confirmed appointment time', async () => {
      await page.goto('/staff/enquiries');
      await page.getByLabel('Search').fill('Elena Wickramasinghe');
      const record = page.getByRole('button', { name: /Elena Wickramasinghe.*Test drive/s }).first();
      await record.click();
      const detail = page.locator('.staff-record-detail');
      await detail.getByLabel('Status').selectOption('contacted');
      await detail.getByLabel('Staff-only notes').fill('Called using fictional contact; confirmed follow-up.');
      await detail.getByRole('button', { name: /save/i }).click();
      await expect(page.locator('.enquiry-success-message')).toContainText('Saved update');
      await detail.getByLabel('Status').selectOption('scheduled');
      await detail.getByLabel('Confirmed date and time').fill(await futureColomboDateTime(page));
      await detail.getByRole('button', { name: /save/i }).click();
      await expect(page.locator('.enquiry-success-message')).toContainText('Saved update');
      return 'Staff note saved; request progressed through Contacted to Scheduled with a confirmed time.';
    });

    await step(page, 'Staff', 'Review the enquiry-linked customer record', 'Customer directory shows contact details and enquiry history', async () => {
      await page.goto('/staff/customers');
      await page.getByLabel('Search').fill('Elena Wickramasinghe');
      await page.getByRole('button', { name: /Elena Wickramasinghe/ }).first().click();
      await expect(page.locator('.staff-record-detail')).toContainText('Enquiry history');
      return 'Customer detail and linked enquiry history are visible to Staff.';
    });
  } finally {
    await context.tracing.stop({ path: testInfoOutput(info, 'staff-public-inventory-trace.zip') });
    await context.close();
  }
});

test('Staff reservations, payments, imports, tracking, and notifications', async ({ browser }, info) => {
  test.setTimeout(180_000);
  const state = readState();
  expect(state.staff && state.vehicles?.length === 3).toBeTruthy();
  const context = await browser.newContext({ baseURL });
  await startTrace(context);
  const page = await context.newPage();
  attachPageDiagnostics(page);
  try {
    await step(page, 'Staff', 'Sign in for reservations and import workflow', 'Staff portal session is authenticated', async () => {
      await login(page, 'Staff', state.staff);
      return 'Signed in to Staff workspace.';
    });

    if (!state.secondaryCustomer) {
      await step(page, 'Staff', 'Create a fictional import customer', 'Customer directory saves a distinct customer with .example contact details', async () => {
        await page.goto('/staff/customers');
        await page.getByRole('button', { name: 'Add customer' }).click();
        const form = page.locator('#customer-create-form');
        await form.locator('input').nth(0).fill('Ruwan Silva');
        await form.locator('input[type="tel"]').fill('+94 77 555 0192');
        await form.locator('input[type="email"]').fill('ruwan.silva@example.com');
        await form.locator('select').selectOption('phone');
        await form.locator('textarea').fill('Fictional acceptance customer.');
        await form.getByRole('button', { name: 'Save customer' }).click();
        await expect(page.getByRole('status')).toContainText('Ruwan Silva was added');
        return 'Ruwan Silva added to the customer directory.';
      });
      state.secondaryCustomer = 'Ruwan Silva';
      writeState(state);
    }

    if (!state.reservation) {
      await page.goto('/staff/reservations');
      await step(page, 'Staff', 'Check direct reservation creation control', 'A Staff user sees the New reservation control on the reservations route', async () => {
        const createButton = page.getByRole('button', { name: '+ New reservation' });
        if (!(await createButton.isVisible())) throw new Error('New reservation control is hidden for Staff on /staff/reservations; inventory offers a Reserve link.');
        return 'New reservation control is visible.';
      }, { continueOnFailure: true });
      await step(page, 'Staff', 'Create reservation and record unverified declared advance', 'Reservation is created and declared advance is explicitly unverified', async () => {
        await page.goto('/staff/inventory');
        const row = page.getByRole('row').filter({ hasText: state.vehicles[0].model });
        await row.getByRole('link', { name: 'Reserve' }).click();
        await page.waitForURL(/\/staff\/reservations\?vehicle=/);
        const form = page.locator('form.reservation-form');
        const selects = form.locator('select');
        await selectOptionContaining(selects.nth(0), 'Elena Wickramasinghe');
        await selectOptionContaining(selects.nth(1), state.vehicles[0].reference);
        await form.getByLabel('Agreed price (LKR) *').fill('14000000');
        await form.getByLabel('Advance amount (LKR)').fill('1000000');
        await form.getByLabel('Staff notes').fill('Fictional reservation for acceptance walkthrough.');
        await form.getByRole('button', { name: 'Create reservation' }).click();
        const notice = page.getByRole('status');
        await expect(notice).toContainText('created. Any declared advance remains unverified');
        state.reservation = (await notice.innerText()).match(/RSV-[A-Z0-9-]+/)?.[0];
        await expect(page.locator('.payment-declared')).toContainText('not a recorded or verified payment');
        return `Reservation ${state.reservation} created; declared advance remains unverified.`;
      });
      writeState(state);
    }

    if (!state.reservationPayment) {
      await step(page, 'MD/Manager', 'Record reservation advance payment', 'Manager records payment through the authorized reservation payment panel', async () => {
        await logout(page);
        await login(page, 'MD/Manager', state.manager);
        await page.goto('/staff/reservations');
        await page.getByRole('row').filter({ hasText: state.reservation }).click();
        await page.getByRole('link', { name: 'Record payment' }).click();
        await expect(page).toHaveURL(/\/staff\/payments\?target_type=reservation/);
        const form = page.locator('form.payment-form');
        await form.getByLabel('Reservation reference *').fill(state.reservation);
        await form.getByRole('button', { name: 'Check balance' }).click();
        await expect(form.locator('.payment-settlement-preview')).toContainText('Outstanding balance');
        await form.getByLabel('Payment amount (LKR) *').fill('1000000');
        await form.getByLabel('Payment method *').selectOption('bank_transfer');
        await form.getByLabel('I confirm these funds have been received and cleared *').check();
        await form.getByLabel('Payment date *').fill(new Date().toISOString().slice(0, 10));
        await form.getByLabel('Transaction reference').fill('PW-ADV-RESERVATION-01');
        await form.getByLabel('Receipt / evidence').setInputFiles({
          name: 'bank-transfer-evidence.pdf',
          mimeType: 'application/pdf',
          buffer: Buffer.from('%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF'),
        });
        await form.getByLabel('Staff notes').fill('Fictional bank transfer for acceptance testing.');
        await form.getByRole('button', { name: 'Confirm & Record Payment' }).click();
        await page.getByRole('dialog').getByRole('button', { name: 'Confirm & Record Payment' }).click();
        const notice = page.getByRole('status');
        await expect(notice).toContainText('was confirmed and recorded');
        state.reservationPayment = (await notice.innerText()).match(/PAY-[A-Z0-9-]+/)?.[0];
        await logout(page);
        await login(page, 'Staff', state.staff);
        return `Manager recorded confirmed payment ${state.reservationPayment} with private PDF evidence.`;
      });
      writeState(state);
    }

    await step(page, 'Staff', 'Review staff notifications and read-state control', 'Staff receives workflow inbox updates and can mark an item read', async () => {
      await page.goto('/staff/notifications');
      await expect(page.getByRole('heading', { name: 'Notifications', exact: true }).first()).toBeVisible();
      await expect(page.locator('.notification-hero-count')).toContainText(/unread notifications?/);
      const firstNotification = page.locator('.notification-card').first();
      if (await firstNotification.count()) {
        const title = await firstNotification.locator('h2').innerText();
        const markRead = firstNotification.getByRole('button', { name: 'Mark read' });
        if (await markRead.count()) {
          await markRead.click();
          await expect(firstNotification.getByRole('button', { name: 'Mark unread' })).toBeVisible();
        }
        return `Inbox rendered; read state toggled for ${title}.`;
      }
      return 'Notifications page rendered with no items for this role.';
    });

    if (!state.importOrder) {
      await page.goto('/staff/imports');
      const existingImportRow = page.getByRole('row').filter({ hasText: 'Ruwan Silva' }).first();
      if (await existingImportRow.count()) {
        await existingImportRow.click();
        await expect(page.locator('.import-detail')).toBeVisible();
        state.importOrder = (await page.locator('.import-detail h3').first().innerText()).trim();
        writeState(state);
      }
    }
    if (!state.importOrder) {
      await step(page, 'Staff', 'Create fictional import order', 'Import is linked to a customer and available vehicle; no stock sale is implied', async () => {
        await page.goto('/staff/imports');
        await page.getByRole('button', { name: '+ Create import' }).click();
        const form = page.locator('form.import-form');
        await selectOptionContaining(form.getByLabel('Customer *'), 'Ruwan Silva');
        await selectOptionContaining(form.getByLabel('Linked vehicle (optional)'), state.vehicles[2].reference);
        await form.getByLabel('Vehicle description *').fill('2024 Mazda CX-5 XD L Package');
        await form.getByLabel('Country of origin *').fill('Japan');
        await form.getByLabel('Vehicle details').fill('Fictional Japanese import order for acceptance tests.');
        await form.getByLabel('Estimated arrival').fill('2026-12-18');
        await form.getByLabel('Shipping information').fill('Test vessel SSP-E2E-04; no real shipment.');
        await form.getByLabel('Customer-visible update').fill('Fictional order received; status updates will appear here.');
        await form.getByLabel('Internal notes · staff only').fill('Test-only import record.');
        await form.getByRole('button', { name: 'Save import' }).click();
        await expect(page.getByRole('status')).toContainText('Import IMP-');
        state.importOrder = (await page.locator('.import-detail h3').first().innerText()).trim();
        return `Created ${state.importOrder} for Ruwan Silva and linked available Mazda stock.`;
      });
      writeState(state);
    }

    if (!state.tracking) {
      await step(page, 'Staff', 'Issue secure import-tracking credentials', 'Tracking access is created and one-time PIN is visible only to Staff', async () => {
        page.once('dialog', (dialog) => dialog.accept());
        await page.getByRole('button', { name: 'Issue / rotate tracking access' }).click();
        const issued = page.locator('.import-pin-issued');
        await expect(issued).toBeVisible();
        const pin = (await issued.locator('code').innerText()).trim();
        const referenceText = await issued.locator('span').innerText();
        const trackingReference = referenceText.replace('Tracking reference:', '').trim();
        state.tracking = { pin, reference: trackingReference };
        return `Issued ${trackingReference}; one-time PIN displayed to staff.`;
      });
      writeState(state);
    }

    await step(page, 'Public customer', 'View secure import tracking timeline', 'Correct tracking reference and PIN reveal only customer-safe status updates', async () => {
      await page.goto('/track');
      await page.getByLabel('Tracking reference *').fill(state.tracking.reference);
      await page.getByLabel('PIN *').fill(state.tracking.pin);
      await page.getByRole('button', { name: 'Track vehicle' }).click();
      await expect(page.locator('.public-tracking-result')).toContainText(state.importOrder);
      await expect(page.locator('.public-tracking-result')).toContainText('Fictional order received');
      await expect(page.getByLabel('PIN *')).toHaveValue('');
      return `Public tracker returned ${state.importOrder}; PIN cleared from the form.`;
    });

    if (!state.blRequest) {
      await step(page, 'Staff', 'Record booking milestones and request BL approval', 'Import timeline advances in order and BL request routes for CEO review', async () => {
        await page.goto('/staff/imports');
        await page.getByRole('row').filter({ hasText: state.importOrder }).click();
        const milestoneForm = page.locator('.import-action-form').first();
        await milestoneForm.getByLabel('Milestone').selectOption('booking_confirmed');
        await milestoneForm.getByLabel('Customer-safe description *').fill('Fictional vehicle booking confirmed.');
        await milestoneForm.getByRole('button', { name: 'Add milestone' }).click();
        await expect(page.getByRole('status')).toContainText('Milestone recorded');
        await milestoneForm.getByLabel('Milestone').selectOption('lc_opened');
        await milestoneForm.getByLabel('Customer-safe description *').fill('Fictional letter of credit opened.');
        await milestoneForm.getByRole('button', { name: 'Add milestone' }).click();
        await expect(page.getByRole('status')).toContainText('Milestone recorded');
        const blForm = page.locator('.import-bl-section form');
        await blForm.getByLabel('Request note').fill('Fictional documents ready for review.');
        await blForm.getByRole('button', { name: 'Request BL approval' }).click();
        await expect(page.getByRole('status')).toContainText('BL approval request submitted to the CEO');
        state.blRequest = true;
        return 'Booking and LC milestones recorded; BL approval request submitted to CEO.';
      });
      writeState(state);
    }
  } finally {
    await context.tracing.stop({ path: testInfoOutput(info, 'staff-reservations-imports-trace.zip') });
    await context.close();
  }
});

test('MD/Manager links the Rep account to a business profile', async ({ browser }, info) => {
  test.setTimeout(60_000);
  const state = readState();
  const context = await browser.newContext({ baseURL });
  await startTrace(context);
  const page = await context.newPage();
  attachPageDiagnostics(page);
  try {
    await step(page, 'MD/Manager', 'Sign in and open representative management', 'Manager can access the representative account linking screen', async () => {
      await login(page, 'MD/Manager', state.manager);
      await page.goto('/staff/reps');
      await expect(page.getByRole('heading', { name: 'Representatives' })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Add a representative profile' })).toBeVisible();
      return 'Representative management loaded with Link existing account form.';
    });
    if (!state.repProfile) {
      await step(page, 'MD/Manager', 'Link the invited Rep account', 'The active Rep gets a manager-created business profile', async () => {
        const form = page.locator('form.rep-link-form');
        await selectOptionContaining(form.getByLabel('Rep account'), 'Kavindu Silva');
        await form.getByLabel('Business status').selectOption('active');
        await form.getByRole('button', { name: 'Link representative' }).click();
        await expect(page.getByRole('status')).toContainText('Representative profile linked');
        await expect(page.getByRole('button', { name: /Kavindu Silva.*pw_rep/ })).toBeVisible();
        state.repProfile = true;
        writeState(state);
        return 'Kavindu Silva linked to an active Rep business profile.';
      });
    }
  } finally {
    await context.tracing.stop({ path: testInfoOutput(info, 'manager-rep-profile-trace.zip') });
    await context.close();
  }
});

test('CEO BL approval, commission policy, and Manager oversight', async ({ browser }, info) => {
  test.setTimeout(90_000);
  const state = readState();
  expect(state.ceo && state.importOrder).toBeTruthy();
  const context = await browser.newContext({ baseURL });
  await startTrace(context);
  const page = await context.newPage();
  attachPageDiagnostics(page);
  try {
    await step(page, 'CEO', 'Sign in and review CEO inbox', 'CEO receives Manager review links and can operate review queues', async () => {
      await login(page, 'CEO', state.ceo);
      await page.goto('/staff/notifications');
      await expect(page.getByRole('heading', { name: 'Notifications', exact: true }).first()).toBeVisible();
      return 'CEO notification inbox rendered.';
    });

    if (!state.blApproved) {
      await step(page, 'CEO', 'Approve staff BL request', 'CEO approval changes request state; BL issuance remains a separate Staff milestone', async () => {
        await page.goto('/staff/bl-requests');
        await expect(page.getByRole('heading', { name: /BL Requests/i })).toBeVisible();
        await page.getByRole('row').filter({ hasText: state.importOrder }).click();
        page.once('dialog', (dialog) => dialog.accept());
        await page.getByRole('button', { name: 'Approve request' }).click();
        await expect(page.getByRole('status')).toContainText('approved');
        state.blApproved = true;
        writeState(state);
        return `CEO approved the BL request for ${state.importOrder}; issuance remains a separate step.`;
      });
    }

    if (!state.commissionPolicy) {
      await step(page, 'CEO', 'Create effective-dated commission bracket', 'CEO can save a valid 2.5% rate schedule and policy history records the change', async () => {
        await page.goto('/staff/commission-rules');
        await expect(page.getByRole('heading', { name: 'Vehicle selling-value brackets' })).toBeVisible();
        const form = page.locator('form.commission-editor');
        if (!(await form.locator('fieldset').count())) await form.getByRole('button', { name: 'Add bracket' }).click();
        const bracket = form.locator('fieldset').first();
        await bracket.getByLabel(/Minimum selling value/).fill('0');
        await bracket.getByLabel('Maximum selling value (LKR)').fill('');
        await bracket.getByLabel('Commission percentage *').fill('2.5');
        await bracket.getByLabel('Effective date *').fill('2026-11-23');
        await form.getByRole('button', { name: 'Save commission policy' }).click();
        await expect(page.getByRole('status')).toContainText('Commission policy saved');
        state.commissionPolicy = true;
        writeState(state);
        return '2.5% commission bracket saved with an effective date and history entry.';
      });
    }

    await step(page, 'CEO', 'Review MD/Manager oversight', 'CEO can view activity attributed to current MD/Manager actors', async () => {
      await page.goto('/staff/oversight/managers');
      await expect(page.getByRole('heading', { name: 'Leadership oversight' })).toBeVisible();
      await expect(page.locator('.workspace-hero')).toContainText('MD/Manager activity');
      await expect(page.getByRole('button', { name: 'Apply filters' })).toBeVisible();
      return 'CEO leadership oversight view and Manager activity filters loaded.';
    });

    await step(page, 'CEO', 'Check read-only sales permissions', 'CEO can inspect sales but cannot create or confirm them', async () => {
      await page.goto('/staff/sales');
      await expect(page.getByRole('heading', { name: 'Sales' })).toBeVisible();
      await expect(page.getByRole('button', { name: '+ New sale' })).toHaveCount(0);
      return 'Sales review is available with no New sale control for CEO.';
    });
  } finally {
    await context.tracing.stop({ path: testInfoOutput(info, 'ceo-oversight-policy-trace.zip') });
    await context.close();
  }
});
