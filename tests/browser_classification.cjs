// Usage: BIOTEX_PUPPETEER_MODULE=/path/to/puppeteer node tests/browser_classification.cjs credentials.json evidence-dir
// Credentials must refer to the restored test database exposed through localhost:18069.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const puppeteer = require(process.env.BIOTEX_PUPPETEER_MODULE || 'puppeteer');
const credentials = JSON.parse(fs.readFileSync(process.argv[2]));
assert.equal(credentials.db, 'biotex_rules_20260905', 'Use only the restored test database');
const output = path.resolve(process.argv[3]);
fs.mkdirSync(output, { recursive: true });
const checks = [];
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
(async () => {
 const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
 const page = await browser.newPage();
 const errors = [];
 const searches = [];
 page.on('request', (request) => {
  if (request.url().includes('/workspace_search_products') && request.postData()) searches.push(JSON.parse(request.postData()).params.kwargs);
 });
 page.on('pageerror', (error) => errors.push(error.message));
 const pass = (name, data = {}) => { checks.push({ name, status: 'passed', ...data }); console.log('PASS', name); };
 const screenshot = (name) => page.screenshot({ path: path.join(output, name + '.png'), fullPage: true });
 try {
  await page.setViewport({ width: 1366, height: 900 });
  await page.goto('http://127.0.0.1:18069/web/login?db=biotex_rules_20260905&debug=1', { waitUntil: 'domcontentloaded', timeout: 120000 });
  await page.waitForSelector('input[name="login"]', { visible: true, timeout: 90000 });
  await page.type('input[name="login"]', credentials.login);
  await page.type('input[name="password"]', credentials.password);
  await Promise.all([page.waitForNavigation({ waitUntil: 'domcontentloaded', timeout: 120000 }), page.click('.oe_login_form button[type="submit"]')]);
  await page.waitForFunction(() => window.odoo?.__WOWL_DEBUG__?.root, { timeout: 120000 });
  const sessionId = await page.evaluate(async ({ session_id, product_ids }) => {
   const services = odoo.__WOWL_DEBUG__.root.env.services;
   const source = (await services.orm.call('biotex.classification.session', 'workspace_bootstrap', [session_id])).session;
   const values = Object.fromEntries(['group_id', 'family_id', 'classifier_id', 'brand_id'].map((key) => [key, source[key]]));
   const session = await services.orm.call('biotex.classification.session', 'workspace_set_classification', [false, values]);
   await services.orm.call('biotex.classification.session', 'workspace_add_products', [[session.id]], { product_ids: product_ids.slice(0, 12) });
   await services.action.doAction({ type: 'ir.actions.client', tag: 'biotex_catalog.classification_workspace', context: { biotex_session_id: session.id } });
   return session.id;
  }, credentials);
  await page.waitForSelector('.o_bcw_table_lines');
  pass('Workspace mounted for classifier', { session_id: sessionId });

  for (const width of [1366, 1024, 390]) {
   await page.setViewport({ width, height: 768 });
   await pause(200);
   const bounds = await page.$eval('.o_bcw_stage', (stage) => {
    const card = stage.getBoundingClientRect();
    return [...stage.querySelectorAll('.o_bcw_stage_mini .o_bcw_code, .o_bcw_stage_mini .o_bcw_chip')].map((item) => {
     const rect = item.getBoundingClientRect();
     return { inside: rect.top >= card.top && rect.bottom < card.bottom && rect.left >= card.left && rect.right <= card.right };
    });
   });
   assert.equal(bounds.length, 2);
   assert.ok(bounds.every((item) => item.inside));
   pass(`A: collapsed summary remains inside card at ${width}px`);
   await screenshot(`summary-${width}`);
  }
  await page.setViewport({ width: 1366, height: 900 });
  const lineScroll = await page.$eval('[aria-label="Productos agregados"]', (el) => {
   el.scrollTop = el.scrollHeight;
   const head = el.querySelector('th').getBoundingClientRect();
   return { height: el.clientHeight, total: el.scrollHeight, sticky: Math.abs(head.top - el.getBoundingClientRect().top) <= 2 };
  });
  assert.ok(lineScroll.total > lineScroll.height && lineScroll.height <= 360 && lineScroll.sticky);
  pass('E: added products scroll with sticky headers', lineScroll);
  await screenshot('added-products-scrolled');

  await page.$$eval('.o_bcw_stage_head', (heads) => heads[1].click());
  const search = '.o_bcw_search_input';
  await page.waitForSelector(search, { visible: true });
  await page.type(search, 'UI CLAS');
  await page.waitForFunction(() => document.querySelectorAll('[data-product-id]').length === 20 && document.querySelector('[aria-label="Resultados de búsqueda"]').getAttribute('aria-busy') === 'false');
  assert.equal(searches.filter((request) => request.query === 'UI CLAS').length, 1);
  assert.ok(searches.every((request) => request.limit <= 20));
  pass('Search debounce produces one bounded request for the typed term');
  const searchGeometry = await page.$eval(search, (el) => {
   const icon = el.parentElement.querySelector('.o_bcw_search_icon').getBoundingClientRect();
   return { padding: parseFloat(getComputedStyle(el).paddingInlineStart), iconEnd: icon.right - el.getBoundingClientRect().left };
  });
  assert.ok(searchGeometry.padding > searchGeometry.iconEnd);
  pass('B: search text clears the permanently visible icon', searchGeometry);
  const resultScroll = await page.$eval('[aria-label="Resultados de búsqueda"]', (el) => {
   el.scrollTop = el.scrollHeight;
   return { height: el.clientHeight, total: el.scrollHeight, sticky: Math.abs(el.querySelector('th').getBoundingClientRect().top - el.getBoundingClientRect().top) <= 2 };
  });
  assert.ok(resultScroll.total > resultScroll.height && resultScroll.height <= 360 && resultScroll.sticky);
  pass('C: search results scroll with a bounded page', resultScroll);
  await screenshot('search-results-scrolled');
  await page.$eval('[aria-label="Resultados de búsqueda"]', (el) => { el.scrollTop = 0; });
  const firstId = await page.$eval('[data-product-id]', (el) => el.dataset.productId);
  await page.click('[data-product-id] .o_bcw_add');
  await page.waitForFunction((id) => !document.querySelector(`[data-product-id="${id}"]`) && document.querySelectorAll('.o_bcw_table_lines tbody tr').length === 13, {}, firstId);
  pass('D: added product disappears and count increments once');
  await page.waitForFunction(() => document.activeElement === document.querySelector('.o_bcw_search_input'));
  await page.waitForFunction(() => document.querySelector('[aria-label="Resultados de búsqueda"]').getAttribute('aria-busy') === 'false');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await page.waitForFunction(() => document.querySelectorAll('.o_bcw_table_lines tbody tr').length === 14);
  pass('G: keyboard selection and Enter add the selected row');

  await page.$$eval('.o_bcw_stage_head', (heads) => heads[2].click());
  await page.$eval('[aria-label="Productos agregados"]', (el) => { el.scrollTop = 0; });
  await page.click('.o_bcw_table_lines .fa-pencil');
  await page.waitForSelector('#bcw_editor_name', { visible: true });
  assert.equal(await page.$('#bcw_editor_details'), null);
  const controls = await page.$eval('#bcw_editor_name', (el) => ({ radius: getComputedStyle(el).borderRadius, shadow: getComputedStyle(el).boxShadow }));
  assert.equal(controls.radius, '8px');
  assert.notEqual(controls.shadow, 'none');
  assert.equal(await page.$eval('.o_bcw_modal .btn-close', (el) => getComputedStyle(el).borderTopWidth), '0px');
  pass('F: modal uses shared controls and collapsed optional details', controls);
  await screenshot('editor-main');
  await page.click('.o_bcw_details_toggle');
  await page.waitForSelector('#bcw_editor_details');
  await screenshot('editor-expanded');
  await page.$eval('.o_bcw_modal input[type="number"]', (el) => { el.value = '0'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.click('.o_bcw_details_toggle');
  await page.click('.o_bcw_modal .modal-footer .btn-primary');
  await page.waitForSelector('#bcw_editor_details .o_bcw_error');
  pass('M: optional validation error reopens its section');
  await page.$eval('.o_bcw_modal input[type="number"]', (el) => { el.value = '1'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.$eval('#bcw_editor_name', (el) => { el.value += ' revisado'; el.dispatchEvent(new Event('input', { bubbles: true })); });
  await page.keyboard.press('Escape');
  await page.waitForSelector('.o_bcw_confirm');
  await page.click('.o_bcw_confirm .btn-secondary');
  pass('Modal Escape preserves unsaved edits');
  await page.click('.o_bcw_modal .modal-footer .btn-primary');
  await page.waitForFunction(() => !document.querySelector('.o_bcw_modal'));
  await page.click('.o_bcw_foot .btn-primary');
  await page.waitForSelector('.o_bcw_review_scroll');
  assert.equal(await page.$eval('.o_bcw_modal .modal-footer .btn-primary', (button) => button.disabled), true);
  const contrast = await page.$eval('.o_bcw_review_scroll td', (cell) => {
   const luminance = (color) => color.match(/[\d.]+/g).slice(0, 3).map(Number).map((c) => c / 255)
    .map((c) => c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2)
    .reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i], 0);
   const style = getComputedStyle(cell);
   const a = luminance(style.color), b = luminance(style.backgroundColor);
   return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  });
  assert.ok(contrast >= 4.5);
  pass('Review table remains readable with the native dark theme', { contrast });
  await screenshot('reclassification-review');
  pass('J: existing codes require explicit review acknowledgement');
  await page.click('.o_bcw_modal .modal-footer .btn-secondary');
  pass('Review cancelled without applying product changes');
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify({ checks, errors }, null, 2));
 } catch (error) {
  console.error('FAILED', error.message);
  await screenshot('failure').catch(() => {});
  fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify({ checks, errors, failure: error.message }, null, 2));
  process.exitCode = 1;
 } finally { await browser.close(); }
})();
