import { chromium } from 'playwright';

const out = process.argv[2];
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1100, height: 1200 } });

// Stub the API so the model-usage page renders without a backend/auth.
const json = (data) => ({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify(data),
});
await page.route('**/api/**', (route) => {
  const url = route.request().url();
  if (url.endsWith('/usage/summary')) return route.fulfill(json([]));
  if (url.endsWith('/config/models'))
    return route.fulfill(
      json({ companies: [{ name: 'OpenAI', models: ['gpt-4o-mini'] }], active: { model: 'gpt-4o-mini', company: 'OpenAI' } }),
    );
  if (url.endsWith('/usage/org-spend')) return route.fulfill(json(null));
  if (url.endsWith('/api-keys/providers')) return route.fulfill(json([]));
  if (url.endsWith('/api-keys')) return route.fulfill(json([]));
  if (url.endsWith('/admin-key')) return route.fulfill(json(null));
  return route.fulfill(json(null));
});

await page.goto('http://localhost:4200/model-usage', { waitUntil: 'networkidle' });
await page.waitForSelector('app-admin-key .admin-card', { timeout: 10000 });
await page.screenshot({ path: `${out}/admin-key-empty.png` });
console.log('captured empty');

// Now with a saved key.
await page.unroute('**/api/**');
await page.route('**/api/**', (route) => {
  const url = route.request().url();
  if (url.endsWith('/admin-key'))
    return route.fulfill(json({ key_hint: 'sk-…b3F9', created_at: '2026-06-30T00:00:00Z' }));
  if (url.endsWith('/usage/summary')) return route.fulfill(json([]));
  if (url.endsWith('/config/models'))
    return route.fulfill(
      json({ companies: [{ name: 'OpenAI', models: ['gpt-4o-mini'] }], active: { model: 'gpt-4o-mini', company: 'OpenAI' } }),
    );
  if (url.endsWith('/usage/org-spend'))
    return route.fulfill(json({ spend_usd: 4.2, since: '2026-06-30T00:00:00Z' }));
  if (url.endsWith('/api-keys/providers')) return route.fulfill(json([]));
  if (url.endsWith('/api-keys')) return route.fulfill(json([]));
  return route.fulfill(json(null));
});
await page.goto('http://localhost:4200/model-usage', { waitUntil: 'networkidle' });
await page.waitForSelector('app-admin-key .key-row', { timeout: 10000 });
await page.screenshot({ path: `${out}/admin-key-saved.png` });
console.log('captured saved');

await browser.close();
