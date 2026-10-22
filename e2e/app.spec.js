import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Journey coverage for the public + buyer surfaces of CarbonX, running against
// the real FastAPI backend (demo mode: DB off) through the real Vite proxy.

test.describe('public surfaces', () => {
  test('landing page renders the product shell', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole('heading', { level: 1 }).first()).toBeVisible();
  });

  test('trust center states what is proven and what is not', async ({ page }) => {
    await page.goto('/trust');
    await expect(
      page.getByRole('heading', { name: /What CarbonX can prove/ })
    ).toBeVisible();
  });

  test('marketplace labels its data source honestly', async ({ page, request }) => {
    await page.goto('/marketplace');
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
});

test.describe('corporate buyer journey (demo credentials, DB-off)', () => {
  test('sign in lands on the ESG desk for the demo corporate', async ({ page }) => {
    await page.goto('/corporate/login');
    await expect(
      page.getByRole('heading', { name: 'Corporate Buyer Sign In' })
    ).toBeVisible();

    await page
      .getByLabel(/Corporate Name/i)
      .fill('Telangana Sustainable Agro Pvt Ltd');
    await page.getByLabel(/Corporate Password/i).fill('Corporate@2026');
    await page
      .getByRole('button', { name: /Sign In to Corporate ESG Desk/i })
      .click();

    await page.waitForURL('**/corporate/dashboard');
    // The dashboard header greets the authenticated buyer by company name.
    await expect(page.getByRole('heading', { level: 1 })).toContainText(
      'Telangana Sustainable Agro'
    );
  });
});

test.describe('accessibility (axe-core)', () => {
  // Gated on the highest-severity class only; lower-severity findings are
  // reviewed and tracked rather than blocking CI.
  for (const path of ['/', '/marketplace']) {
    test(`no critical accessibility violations on ${path}`, async ({ page }) => {
      await page.goto(path);
      // Wait for network to settle so async content is in the DOM before scan.
      await page.waitForLoadState('networkidle');
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
