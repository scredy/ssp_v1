import { test, expect } from 'playwright/test';
import { mkdir } from 'node:fs/promises';

const photo = (id) => ({ id, url: `/api/vehicle-photos/${id}/`, content_type: 'image/png', created_at: '2026-01-01T00:00:00Z' });
const vehicle = (id, make, model, condition = 'used') => ({
  reference: `TEST-${id}`, make, model, variant: '', manufacture_year: 2024,
  mileage_km: 12000, fuel_type: 'petrol', transmission: 'automatic', color: 'White',
  condition, asking_price_lkr: '12500000.00', description: 'Fictional Playwright vehicle fixture.',
  photos: [photo(id)], visibility: 'published', status: 'available',
});

const twoVehicles = [vehicle(1, 'Honda', 'HR-V'), vehicle(2, 'Toyota', 'Corolla', 'new')];
const fourVehicles = [
  vehicle(1, 'Honda', 'HR-V'), vehicle(2, 'Toyota', 'Corolla', 'new'),
  vehicle(3, 'BMW', 'X1'), vehicle(4, 'Subaru', 'Forester'),
];

async function mockInventory(page, inventory) {
  let requests = 0;
  await page.route('**/api/cars**', async (route) => {
    requests += 1;
    await new Promise((resolve) => setTimeout(resolve, 120));
    await route.fulfill({ json: inventory, headers: { 'Cache-Control': 'no-store' } });
  });
  await page.route('**/api/vehicle-photos/**', (route) => route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l7sAAAAASUVORK5CYII=', 'base64'),
  }));
  return () => requests;
}

test('small inventory stays static and homepage search uses live options', async ({ page }) => {
  const requestCount = await mockInventory(page, twoVehicles);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.locator('.public-vehicle-card')).toHaveCount(2);
  await expect(page.getByRole('heading', { name: 'Featured vehicles' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Pause motion' })).toBeVisible();
  await expect(page.locator('.public-vehicle-grid')).not.toHaveClass(/is-carousel/);
  await expect(page.locator('.manufacturer-marquee')).toHaveClass(/is-moving/);
  expect(requestCount()).toBe(1);

  const featuredTop = await page.locator('.featured-section').evaluate((element) => element.getBoundingClientRect().top);
  expect(featuredTop).toBeGreaterThan(900);
  const manufacturerLinks = page.locator('.manufacturer-marquee-track a');
  await expect(manufacturerLinks).toHaveCount(40);
  await expect(manufacturerLinks.first()).toHaveAttribute('href', '/cars?make=Toyota');
  await expect(manufacturerLinks.nth(14)).toHaveAttribute('aria-label', 'Browse Volkswagen vehicles');
  const brandLinks = await manufacturerLinks.evaluateAll(links => links.map(link => link.getAttribute('href')));
  expect(new Set(brandLinks.slice(0, 20)).size).toBe(20);
  expect(brandLinks.slice(20)).toEqual(brandLinks.slice(0, 20));
  await expect(page.locator('.quick-search')).toHaveCSS('opacity', '1');
  await page.screenshot({ path: 'artifacts/screenshots/homepage-desktop-polish.png' });

  for (const selector of ['.featured-section', '.service-section', '.business-intro', '.home-contact']) {
    const section = page.locator(selector);
    await section.scrollIntoViewIfNeeded();
    await expect(section).toHaveCSS('opacity', '1');
    await expect(section).not.toHaveClass(/is-pending/);
  }
  await page.screenshot({ path: 'artifacts/screenshots/homepage-sections-desktop.png', fullPage: true });

  await page.getByLabel('Condition').selectOption('used');
  await page.getByLabel('Make').selectOption('Honda');
  await expect(page.getByLabel('Model').locator('option')).toHaveText(['All Models', 'HR-V']);
  await page.getByLabel('Model').selectOption('HR-V');
  await page.getByRole('button', { name: 'Search vehicles' }).click();
  await expect(page).toHaveURL(/\/cars\?condition=used&make=Honda&model=HR-V$/);
});

test('larger inventory enables marquee pause and carousel controls', async ({ page }) => {
  await mockInventory(page, fourVehicles);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.locator('.public-vehicle-card')).toHaveCount(4);
  await expect(page.locator('.public-vehicle-grid')).toHaveClass(/is-carousel/);
  const marquee = page.locator('.manufacturer-marquee');
  await expect(page.getByRole('button', { name: 'Pause motion' })).toBeVisible();
  await expect(marquee.locator('.manufacturer-marquee-track a')).toHaveCount(40);
  expect(await marquee.locator('.manufacturer-marquee-track').evaluate((element) => getComputedStyle(element).animationName)).toBe('manufacturer-scroll');

  await marquee.focus();
  expect(await marquee.locator('.manufacturer-marquee-track').evaluate((element) => getComputedStyle(element).animationPlayState)).toBe('paused');
  await page.getByRole('button', { name: 'Pause motion' }).click();
  await expect(page.getByRole('button', { name: 'Resume motion' })).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Resume motion' }).click();

  const track = page.locator('.public-vehicle-grid.is-carousel');
  expect(await track.evaluate((element) => getComputedStyle(element).scrollSnapType)).toContain('x');
  await page.getByRole('button', { name: 'Show next vehicles' }).click();
  await expect.poll(() => track.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  await page.locator('.vehicle-card-image img').first().hover();
  await expect.poll(() => page.locator('.vehicle-card-image img').first().evaluate((element) => getComputedStyle(element).transform)).not.toBe('none');
  await page.getByRole('button', { name: 'Pause motion' }).click();
  await page.getByRole('link', { name: 'Browse BMW vehicles' }).first().click();
  await expect(page).toHaveURL(/\/cars\?make=BMW$/);
});

test('mobile first viewport and reduced motion remain accessible', async ({ page }) => {
  await mockInventory(page, fourVehicles);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.locator('.public-vehicle-card')).toHaveCount(4);
  await expect(page.locator('.public-vehicle-grid')).toHaveClass(/is-carousel/);
  const featuredTop = await page.locator('.featured-section').evaluate((element) => element.getBoundingClientRect().top);
  const searchBottom = await page.locator('.quick-search').evaluate(
    element => element.getBoundingClientRect().bottom
  );
  const manufacturersBottom = await page.locator('.manufacturer-strip').evaluate(
    element => element.getBoundingClientRect().bottom
  );

  expect(searchBottom).toBeLessThanOrEqual(844);
  expect(featuredTop).toBeGreaterThanOrEqual(manufacturersBottom);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(await page.locator('.approved-hero-image').evaluate((element) => getComputedStyle(element).animationName)).toBe('none');
  expect(await page.locator('.manufacturer-marquee-track').evaluate((element) => getComputedStyle(element).animationName)).toBe('none');
  expect(await page.locator('.public-vehicle-grid.is-carousel').evaluate((element) => getComputedStyle(element).scrollSnapType)).toContain('x');
  await page.screenshot({ path: 'artifacts/screenshots/homepage-mobile-polish.png' });
  await page.screenshot({ path: 'artifacts/screenshots/homepage-sections-mobile.png', fullPage: true });

  await page.getByRole('button', { name: 'Open navigation' }).click();
  await expect(page.getByRole('navigation', { name: 'Mobile navigation' }).getByRole('link', { name: 'Vehicles' })).toBeVisible();
  await page.getByRole('button', { name: 'Close navigation' }).click();
  await expect(page.getByRole('button', { name: 'Open navigation' })).toBeVisible();
});

test('hero vehicles and manufacturer logos move independently with real vehicle images', async ({ browser }) => {
  test.setTimeout(60_000);
  await mkdir('artifacts/screenshots', { recursive: true });
  await mkdir('artifacts/videos', { recursive: true });
  const context = await browser.newContext({
    baseURL: process.env.SSP_TEST_BASE_URL ?? 'http://localhost:3100',
    viewport: { width: 1440, height: 900 },
    recordVideo: { dir: 'artifacts/videos', size: { width: 1440, height: 900 } },
  });
  const page = await context.newPage();
  const heroResponses = [];
  page.on('response', (response) => {
    if (/\/images\/(?:home-audi-a5-ssp|defender-110-silver|bmw-m4-white|mercedes-g63-black|porsche-911-yellow)\.webp(?:\?|$)/.test(response.url())) {
      heroResponses.push({ url: new URL(response.url()).pathname, status: response.status() });
    }
  });
  // Inventory is mocked for determinism; no image request is intercepted.
  await page.route('**/api/cars**', (route) => route.fulfill({ json: twoVehicles.map((item) => ({ ...item, photos: [] })) }));
  try {
    await page.goto('/');
    const visual = page.locator('.approved-hero-visual');
    const car = page.locator('.approved-hero-image');
    const vehicles = [
      ['Audi A5', 'home-audi-a5-ssp'],
      ['Land Rover Defender 110', 'defender-110-silver'],
      ['BMW M4', 'bmw-m4-white'],
      ['Mercedes-AMG G63', 'mercedes-g63-black'],
      ['Porsche 911', 'porsche-911-yellow'],
    ];
    const observed = new Set();
    const captureCenteredVehicle = async ([name, slug]) => {
      const dimensions = slug === 'home-audi-a5-ssp'
        ? [1679, 937]
        : [1220, 711];

      await expect.poll(async () => visual.evaluate(element => {
        const image = element.querySelector('img');
        return {
          label: element.getAttribute('aria-label'),
          centered: element.classList.contains('hero-phase-center'),
          src: image?.getAttribute('src'),
          dimensions: image?.complete
            ? [image.naturalWidth, image.naturalHeight]
            : [0, 0],
        };
      }), { timeout: 12000 }).toEqual({
        label: `Featured vehicle: ${name}`,
        centered: true,
        src: `/images/${slug}.webp`,
        dimensions,
      });
      observed.add(name);
      await page.screenshot({ path: `artifacts/screenshots/home-vehicle-${slug}.png` });
    };

    await captureCenteredVehicle(vehicles[0]);
    for (const vehicle of vehicles.slice(1)) {
      await expect(visual).toHaveClass(/hero-phase-exit/, { timeout: 9000 });
      await expect(visual).toHaveAttribute('aria-label', `Featured vehicle: ${vehicle[0]}`, { timeout: 9000 });
      await expect(visual).toHaveClass(/hero-phase-enter/, { timeout: 9000 });
      const enteringX = await car.evaluate((element) => element.getBoundingClientRect().x);
      await expect.poll(
        async () => Math.abs(
          await car.evaluate(element => element.getBoundingClientRect().x)
          - enteringX
        ),
        { timeout: 2000, intervals: [50, 100, 150, 200] }
      ).toBeGreaterThan(40);
      await captureCenteredVehicle(vehicle);
    }

    const marquee = page.locator('.manufacturer-marquee-track');
    const brandX = await marquee.evaluate((element) => element.getBoundingClientRect().x);
    await page.waitForTimeout(500);
    expect(await marquee.evaluate((element) => element.getBoundingClientRect().x)).not.toBe(brandX);

    // Wait for the next Audi to enter and reach center to verify a full loop.
    await expect(visual).toHaveClass(/hero-phase-exit/, { timeout: 9000 });
    await expect(visual).toHaveAttribute('aria-label', 'Featured vehicle: Audi A5', { timeout: 9000 });
    await expect(visual).toHaveClass(/hero-phase-enter/, { timeout: 9000 });
    const loopStartX = await car.evaluate((element) => element.getBoundingClientRect().x);
    await expect.poll(
      async () => Math.abs(
        await car.evaluate(element => element.getBoundingClientRect().x)
        - loopStartX
      ),
      { timeout: 2000, intervals: [50, 100, 150, 200] }
    ).toBeGreaterThan(40);
    await captureCenteredVehicle(vehicles[0]);

    expect([...observed]).toEqual(vehicles.map(([name]) => name));
    for (const [, slug] of vehicles) {
      expect(heroResponses.some((response) => response.url === `/images/${slug}.webp` && response.status === 200), `${slug} must load from the app with HTTP 200`).toBe(true);
    }
    expect(observed.size).toBe(5);
  } finally {
    const video = page.video();
    await context.close();
    if (video) await video.saveAs('artifacts/videos/homepage-five-car-cycle.webm');
  }
});
test('public service pages and staff sign-in render without submitting forms', async ({ page }) => {
  const routes = [
    ['/finance', 'Finance calculator'],
    ['/track', 'Track your vehicle'],
    ['/contact', 'Let’s talk vehicles.'],
    ['/request-quote', 'Request a quote'],
    ['/book-appointment', 'Book an appointment'],
    ['/staff/login', 'Sign in'],
  ];

  for (const [path, heading] of routes) {
    const response = await page.goto(path);
    expect(response?.status(), `${path} response`).toBeLessThan(400);
    await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
  }

  await expect(page.getByRole('button', { name: 'Sign in securely' })).toBeVisible();
  await expect(page.locator('form')).toHaveCount(1);
});

test('homepage sections stay visible when client JavaScript is unavailable', async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  await page.goto('/');
  for (const selector of ['.featured-section', '.service-section', '.business-intro', '.home-contact']) {
    await expect(page.locator(selector)).toBeVisible();
    expect(await page.locator(selector).evaluate((element) => getComputedStyle(element).opacity)).toBe('1');
  }
  await context.close();
});
