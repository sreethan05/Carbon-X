import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Journey coverage for the public + buyer surfaces of CarbonX, running against
// the real FastAPI backend (demo mode: DB off) through the real Vite proxy.

test.beforeEach(async ({ context }) => {
  // CI exercises the browser app without depending on Google Fonts availability.
  await context.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) => route.abort());
});

test.describe('public surfaces', () => {
  test('landing page renders the product shell', async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' });
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
  });

  test('trust center states what is proven and what is not', async ({ page }) => {
    await page.goto('/trust', { waitUntil: 'domcontentloaded' });
    await expect(
      page.getByRole('heading', { name: /What CarbonX can prove/ })
    ).toBeVisible();
  });

  test('marketplace labels its data source honestly', async ({ page, request }) => {
    await page.goto('/marketplace', { waitUntil: 'domcontentloaded' });
    await expect(
      page.getByRole('heading', { name: 'Carbon Credit Marketplace' })
    ).toBeVisible();

    // Ask the API which source it is serving and assert the UI agrees.
    // CI / no-DB runs must show the SAMPLE DATA badge; live-DB runs (local
    // machine with Supabase creds) must NOT. Either way, honesty holds.
    const listings = await (await request.get('/py-api/marketplace/listings')).json();
    const isFallback = listings?.source === 'fallback';
    const badge = page.getByText('SAMPLE DATA (DB offline)');
    if (isFallback) {
      await expect(badge).toBeVisible();
    } else {
      await expect(badge).toBeHidden();
    }
    // Budget-relevant honesty line the buyers cannot miss.
    await expect(
      page.getByText(/proxy estimates until field validation passes/i).first()
    ).toBeVisible();
  });

  test('mobile workspace navigation and marketplace status filters stay usable', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/marketplace', { waitUntil: 'domcontentloaded' });

    const dock = page.getByRole('navigation', { name: 'Quick navigation' });
    await expect(dock.getByRole('link', { name: 'Market' })).toHaveAttribute('aria-current', 'page');
    await page.getByRole('button', { name: 'Open menu' }).click();
    const menu = page.getByRole('navigation', { name: 'Workspace navigation' });
    await expect(menu.getByRole('link', { name: 'Verify a certificate' })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(menu).toBeHidden();

    await expect(page.getByRole('button', { name: 'Buy Credits' }).first()).toBeVisible();
    const allStatuses = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname === '/py-api/marketplace/listings' && url.searchParams.get('status') === 'all';
    });
    await page.getByRole('button', { name: 'All Statuses' }).click();
    expect((await allStatuses).ok()).toBeTruthy();
    await expect(page.getByRole('button', { name: 'All Statuses' })).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: 'Reset filters' }).click();
    await expect(page.getByRole('button', { name: 'Active Only' })).toHaveAttribute('aria-pressed', 'true');
  });
});

test.describe('corporate buyer journey (demo credentials, DB-off)', () => {
  async function signInBuyer(page) {
    await page.goto('/corporate/login', { waitUntil: 'domcontentloaded' });
    await page.getByLabel(/Corporate Name/i).fill('Telangana Sustainable Agro Pvt Ltd');
    await page.getByLabel(/Corporate Password/i).fill('Corporate@2026');
    await page.getByRole('button', { name: /Sign In to Corporate ESG Desk/i }).click();
    await expect(page).toHaveURL(/\/corporate\/dashboard$/);
  }

  test('sign in lands on the ESG desk for the demo corporate', async ({ page }) => {
    const consoleErrors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    await signInBuyer(page);
    // The dashboard header greets the authenticated buyer by company name.
    await expect(page.getByRole('heading', { level: 1 })).toContainText(
      'Telangana Sustainable Agro'
    );
    expect(consoleErrors.filter((message) => /same key|unique key/i.test(message))).toEqual([]);
  });

  test('simulated mobile checkout records a split and opens the retired certificate', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await signInBuyer(page);
    await page.goto('/marketplace', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('SAMPLE DATA (DB offline)')).toBeVisible();
    await page.getByRole('button', { name: 'Buy Credits', exact: true }).first().click();
    const checkout = page.getByRole('dialog', { name: 'Confirm Credit Escrow Purchase' });
    const response = page.waitForResponse(
      (res) => res.url().endsWith('/py-api/payments/checkout') && res.request().method() === 'POST'
    );
    await checkout.getByRole('button', { name: 'Confirm & Lock Escrow' }).click();
    const receipt = await (await response).json();
    expect(receipt.simulated).toBe(true);
    expect(receipt.settlement.certificate_id).toMatch(/^CX-/);
    await expect(checkout.getByText('Simulated purchase complete — credits retired')).toBeVisible();
    await expect(checkout.getByText(/No money moved/)).toBeVisible();
    await expect(checkout.getByText(/Transparent payout split/)).toBeVisible();
    await checkout.getByRole('button', { name: 'View Certificate' }).click();
    await expect(page).toHaveURL(`/buyer/certificates/${receipt.settlement.certificate_id}`);
    await expect(page.getByRole('heading', { name: 'Agricultural Carbon Credit Certificate' })).toBeVisible();
    await expect(page.getByText('STATUS: RETIRED', { exact: true })).toBeVisible();
  });

  test('an unconfirmed checkout response does not trigger a second purchase', async ({ page }) => {
    await signInBuyer(page);
    let fallbackRequests = 0;
    await page.route('**/py-api/marketplace/buy', async (route) => {
      fallbackRequests += 1;
      await route.abort();
    });
    await page.route('**/py-api/payments/checkout', (route) => route.fulfill({
      status: 502,
      contentType: 'text/plain',
      body: 'Connection lost after submitting checkout',
    }));
    await page.goto('/marketplace', { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: 'Buy Credits', exact: true }).first().click();
    const checkout = page.getByRole('dialog', { name: 'Confirm Credit Escrow Purchase' });
    await checkout.getByRole('button', { name: 'Confirm & Lock Escrow' }).click();
    await expect(checkout.getByText(/Check your certificates and payment status/)).toBeVisible();
    expect(fallbackRequests).toBe(0);
  });

  test('bulk checkout keeps completed receipts when the next parcel is unavailable', async ({ page }) => {
    await signInBuyer(page);
    let attempts = 0;
    await page.route('**/py-api/payments/checkout', async (route) => {
      attempts += 1;
      if (attempts === 1) {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 409,
        json: { success: false, message: 'Listing is no longer available.' },
      });
    });
    await page.goto('/marketplace/checkout', { waitUntil: 'domcontentloaded' });
    const matches = page.waitForResponse((res) =>
      res.url().endsWith('/py-api/marketplace/auto-match') && res.request().postDataJSON()?.target_volume === 250
    );
    await page.getByRole('spinbutton', { name: 'Target Offset Volume (MT CO2e)' }).fill('250');
    expect((await (await matches).json()).matched_farms.length).toBeGreaterThan(1);
    await page.getByRole('button', { name: 'Proceed to Escrow Checkout' }).click();
    const checkout = page.getByRole('dialog', { name: 'Bulk escrow checkout' });
    await checkout.getByRole('button', { name: 'Submit escrow purchases' }).click();
    await expect(checkout.getByText('1 recorded settlement(s)')).toBeVisible();
    await expect(checkout.getByRole('button', { name: /^CX-/ })).toBeVisible();
    await expect(checkout.getByRole('alert')).toContainText('Listing is no longer available.');
    expect(attempts).toBe(2);
  });
});

test.describe('accessibility (axe-core)', () => {
  const gatedRoutes = ['/', '/marketplace', '/trust', '/corporate/login'];

  for (const path of gatedRoutes) {
    test(`no critical accessibility violations on ${path}`, async ({ page }) => {
      await page.goto(path, { waitUntil: 'domcontentloaded' });
      // Wait for the lazy route itself so axe cannot scan the loading screen.
      await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
      const axe = new AxeBuilder({ page });
      const results = await axe.analyze();
      const critical = results.violations.filter((v) => v.impact === 'critical');
      expect
        .soft(
          critical.map((v) => `${v.id}: ${v.nodes.length} node(s)`).join('\n'),
          `critical violations on ${path}`
        )
        .toBe('');
      expect(critical).toHaveLength(0);
    });
  }
});
