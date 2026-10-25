import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

// Farmer-side journeys: demo login -> dashboard -> farm-mapping guardrail ->
// carbon passport -> wallet -> support request. Runs against the real FastAPI
// backend (demo mode: DB off) through the real Vite proxy, the same topology
// production deployments reverse-proxy.
//
// Honesty being asserted here:
// - the farm map refuses to submit a parcel without a drawn boundary,
// - the wallet states the 70% settlement floor (not a payout promise),
// - currency flows visible to the farmer show the trust engine and ledger,
// - a grievance lands in "My Requests" tracked to a written resolution.

const DEMO_LOGIN_NOTE =
  'demo login requires the DB-off demo backend (see playwright.config.js)';

async function startDemoFarmerSession(request, page) {
  const res = await request.post('/py-api/demo/login', { data: {} });
  const session = await res.json();
  expect(
    session.success,
    `${DEMO_LOGIN_NOTE}: ${session?.message ?? res.status()}`,
  ).toBeTruthy();

  // Seed the same localStorage keys the app's AuthContext uses, so protected
  // routes resolve without re-driving the login form in every test.
  await page.addInitScript(
    ({ token, user }) => {
      localStorage.setItem('carbonx_token', token);
      localStorage.setItem('carbonx_user', JSON.stringify(user));
    },
    { token: session.token, user: session.user },
  );
  return session.user;
}

test.describe('farmer demo session (demo credentials, DB-off)', () => {
  test('demo login opens the farmer dashboard', async ({ page }) => {
    await page.goto('/farmer/login');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

    await page
      .getByRole('button', { name: /Explore in Demo Mode/i })
      .click();
    await page.waitForURL('**/farmer/dashboard');

    // The dashboard greets the demo farmer ("Venkat Rao", the sample profile
    // documented in AGENTS.md) and surfaces the action rail.
    await expect(page.getByRole('heading', { level: 1 })).toContainText(
      'Venkat Rao',
    );
    await expect(
      page.getByRole('heading', { name: 'Farm Management & Marketplace Actions' })
    ).toBeVisible();
  });

  test('farm mapping refuses to submit without a drawn parcel boundary', async ({
    page,
    request,
  }) => {
    await startDemoFarmerSession(request, page);
    await page.goto('/farm-map');

    // The honest instruction and the disabled-gate are the guardrail: no
    // polygon, no proceeding to crop details / satellite scan.
    await expect(
      page.getByText(/Draw your parcel boundary on the map/i)
    ).toBeVisible();
    const proceed = page.getByRole('button', {
      name: /Confirm Boundary & Proceed/i,
    });
    await expect(proceed).toBeDisabled();
  });

  test('carbon passport shows analytics and the trust & ledger card', async ({
    page,
    request,
  }) => {
    await startDemoFarmerSession(request, page);
    await page.goto('/farmer/dashboard');

    await page.getByRole('button', { name: /Carbon Passport NDVI biomass/ }).click();
    // The dashboard may open the passport at /farmer/passport/:id or fall back
    // to /farm-analytics — assert the rendered outcome, not one URL shape.
    await expect(
      page.getByRole('heading', { level: 1 }).filter({
        hasText: 'Multi-Season Analytics & Passport',
      })
    ).toBeVisible();
    // The farmer sees the verification state machine on every farm he owns.
    await expect(
      page.getByText(/Trust Engine & Tamper-Evident Ledger/)
    ).toBeVisible();
  });

  test('wallet states the 70% settlement floor, not a payout promise', async ({
    page,
    request,
  }) => {
    await startDemoFarmerSession(request, page);
    await page.goto('/farmer/wallet');

    await expect(
      page.getByRole('heading', { level: 1 }).filter({ hasText: 'Farmer Carbon Wallet' })
    ).toBeVisible();
    await expect(
      page.getByText(/70% farmer floor on the immutable ledger/)
    ).toBeVisible();
    // Payout rails are labelled simulated until regulatory pilot clearance.
    await expect(
      page.getByText(/simulated until regulatory pilot clearance/)
    ).toBeVisible();
  });

  test('support request lands in My Requests tracked to a written resolution', async ({
    page,
  }) => {
    const uniqueTitle = `Boundary misses the south canal (E2E ${Date.now()})`;

    // Drive the same demo-login flow a real farmer would (see test 1), then
    // file a grievance from the Support page and watch it land in My Requests.
    await page.goto('/farmer/login');
    await page.getByRole('button', { name: /Explore in Demo Mode/i }).click();
    await page.waitForURL('**/farmer/dashboard');
    await page.getByRole('button', { name: 'Support' }).click();
    await page.waitForURL('**/support');
    // Let the SupportCenter mount (ticket list + form) after client-side nav.
    await page.getByText('My Requests').waitFor();

    await expect(
      page.getByRole('heading', { name: 'Support & Transparency Center' })
    ).toBeVisible();

    await page
      .getByPlaceholder('Short title (e.g. Boundary misses the south canal)')
      .fill(uniqueTitle);
    await page
      .getByPlaceholder(
        'Describe what is wrong, what should change, and when it started.'
      )
      .fill(
        'The mapped polygon misses the south canal strip near the pump; fix the boundary and re-check the estimate.'
      );

    await page.getByRole('button', { name: 'File request' }).click();

    // The reporter's tracker shows the ticket with its lifecycle status —
    // requests resolve in writing (resolution/staff note), never by editing history.
    await expect(page.getByText('Request filed')).toBeVisible();
    const row = page
      .locator('div.rounded-xl.border')
      .filter({ hasText: uniqueTitle })
      .first();
    await expect(row).toBeVisible();
    await expect(row.getByText('Open', { exact: true })).toBeVisible();
  });
});

test.describe('accessibility (axe-core, farmer surfaces)', () => {
  const gatedRoutes = ['/farmer/dashboard', '/farmer/wallet', '/support'];

  for (const path of gatedRoutes) {
    test(`no critical accessibility violations on ${path}`, async ({
      page,
      request,
    }) => {
      await startDemoFarmerSession(request, page);
      await page.goto(path);
      // Same settle discipline as app.spec.js: domcontentloaded + settle,
      // networkidle proved brittle on dev servers.
      await page.waitForLoadState('domcontentloaded');
      await page.waitForTimeout(2000);
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
