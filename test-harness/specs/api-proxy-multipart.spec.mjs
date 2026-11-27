import { test, expect } from 'playwright/test';

test('same-origin API proxy forwards multipart photo bodies with their boundary', async ({ page }) => {
  await page.goto('/');
  const result = await page.evaluate(async () => {
    const form = new FormData();
    form.append('photos', new File([new Uint8Array([137, 80, 78, 71])], 'proxy-check.png', { type: 'image/png' }));
    const response = await fetch('/api/staff/inventory/SSP-PROXY-CHECK/photos/', {
      method: 'POST', body: form, credentials: 'same-origin',
    });
    return { status: response.status, body: await response.json() };
  });
  expect(result.status).toBe(200);
  expect(result.body.contentType).toMatch(/^multipart\/form-data; boundary=/);
  expect(result.body.bodyBytes).toBeGreaterThan(0);
  expect(result.body.hasPhotoField).toBe(true);
  expect(result.body.hasFilename).toBe(true);
});
