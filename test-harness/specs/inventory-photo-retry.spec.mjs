import { test, expect } from 'playwright/test';

const vehicle = {
  id: 41, reference: 'SSP-TESTPHOTO41', make: 'Toyota', model: 'Prius', variant: '',
  manufacture_year: 2022, mileage_km: 12000, fuel_type: 'hybrid', transmission: 'automatic',
  color: 'Silver', condition: 'used', asking_price_lkr: '12500000.00', description: 'Test fixture',
  photos: [], visibility: 'draft', status: 'available', internal_identifier: 'PHOTO-RETRY-41',
};

test('created vehicle stays editable and retries photos without creating another vehicle', async ({ page }) => {
  let createRequests = 0;
  let photoRequests = 0;
  let saved = null;
  const forwardedRequests = [];

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();
    if (method === 'GET' && url.pathname === '/api/auth/me') {
      return route.fulfill({ json: { username: 'staff', first_name: 'Test', last_name: 'Staff', role: 'staff', account_type: 'internal', is_superuser: false } });
    }
    if (method === 'GET' && url.pathname === '/api/staff/inventory') {
      return route.fulfill({ json: saved ? [saved] : [] });
    }
    if (method === 'GET' && url.pathname === '/api/auth/csrf') {
      return route.fulfill({ json: { detail: 'CSRF cookie set' } });
    }
    if (method === 'POST' && url.pathname === '/api/staff/inventory') {
      createRequests += 1;
      saved = { ...vehicle, ...JSON.parse(request.postData()) };
      return route.fulfill({ status: 201, json: saved });
    }
    if (url.pathname === `/api/staff/inventory/${vehicle.reference}` && method === 'PATCH') {
      saved = { ...saved, ...JSON.parse(request.postData()) };
      return route.fulfill({ status: 200, json: saved });
    }
    if (url.pathname === `/api/staff/inventory/${vehicle.reference}/photos` && method === 'POST') {
      photoRequests += 1;
      forwardedRequests.push({ origin: url.origin, contentType: request.headers()['content-type'], body: request.postDataBuffer() });
      if (photoRequests === 1) return route.fulfill({ status: 503, json: { detail: 'Storage temporarily unavailable.' } });
      saved = { ...saved, photos: [{ id: 71, url: '/api/vehicle-photos/71/', content_type: 'image/png', created_at: '2026-11-27T10:00:00Z' }] };
      return route.fulfill({ status: 201, json: saved });
    }
    return route.fulfill({ status: 404, json: { detail: `Unexpected request ${method} ${url.pathname}` } });
  });

  await page.goto('/staff/inventory');
  await expect(page.getByRole('main').getByRole('heading', { name: 'Vehicle inventory' })).toBeVisible();
  await page.getByRole('button', { name: '+ Add vehicle' }).click();
  await page.getByLabel('Make', { exact: true }).fill('Toyota');
  await page.getByLabel('Model', { exact: true }).fill('Prius');
  await page.getByLabel('Color', { exact: true }).fill('Silver');
  await page.getByLabel('Chassis / VIN / stock ID').fill('PHOTO-RETRY-41');
  await page.getByLabel('Asking price (LKR)').fill('12500000');
  await page.getByLabel('Add photographs').setInputFiles({
    name: 'prius.png', mimeType: 'image/png',
    buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l7sAAAAASUVORK5CYII=', 'base64'),
  });

  await page.getByRole('button', { name: 'Create vehicle' }).click();
  await expect(page.getByRole('heading', { name: 'Update vehicle details' })).toBeVisible();
  await expect(page.locator('.inventory-message.is-error')).toHaveText('Vehicle details saved. Photo upload failed: Storage temporarily unavailable. You can retry the photographs without creating another vehicle.');
  await expect(page.getByRole('button', { name: 'Retry photo upload' })).toBeVisible();
  await expect(page.getByText(vehicle.reference).first()).toBeVisible();

  await page.getByRole('button', { name: 'Retry photo upload' }).click();
  await expect(page.getByRole('status')).toHaveText(`Saved ${vehicle.reference}.`);
  expect(createRequests).toBe(1);
  expect(photoRequests).toBe(2);
  expect(forwardedRequests.every((request) => request.origin === new URL(page.url()).origin)).toBe(true);
  expect(forwardedRequests.every((request) => request.contentType.startsWith('multipart/form-data; boundary=') && request.body?.includes(Buffer.from('name="photos"')))).toBe(true);
});
