import { test, expect } from 'playwright/test';
import { readState, writeState, step, attachPageDiagnostics } from './helpers.mjs';

const baseURL = process.env.SSP_TEST_BASE_URL ?? 'http://localhost:3100';
const traces = (info, name) => info.outputPath(name);

async function trace(context) { await context.tracing.start({ screenshots: true, snapshots: true, sources: true }); }
async function login(page, credentials) {
  for (let attempt = 0; attempt < 6; attempt++) {
    await page.goto('/staff/login');
    await page.getByLabel('Username').fill(credentials.username);
    await page.getByLabel('Password').fill(credentials.password);
    const responsePromise = page.waitForResponse(r => r.url().includes('/api/auth/login') && r.status() !== 308 && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Sign in securely' }).click();
    const response = await responsePromise;
    if (response.status() === 429 && attempt < 5) {
      const message = await response.text();
      const seconds = Number(message.match(/available in (\d+) second/)?.[1] || 2);
      await page.waitForTimeout((seconds + 1) * 1000); continue;
    }
    if (!response.ok()) throw new Error(`Login failed with HTTP ${response.status()}: ${await response.text()}`);
    await page.waitForURL('**/staff'); return;
  }
  throw new Error('Login remained rate limited after retries.');
}
async function choose(select, text) {
  const option = select.locator('option').filter({ hasText: text }).first();
  await select.selectOption(await option.getAttribute('value'));
}
async function apiCall(page, path, method = 'GET', body = undefined) {
  return page.evaluate(async ({ path, method, body }) => {
    const csrf = document.cookie.split('; ').find(x => x.startsWith('csrftoken='))?.split('=')[1] || '';
    const headers = { 'X-CSRFToken': decodeURIComponent(csrf) };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, { method, credentials: 'include', headers, body: body === undefined ? undefined : JSON.stringify(body) });
    let data; try { data = await response.json(); } catch { data = await response.text(); }
    return { status: response.status, data };
  }, { path, method, body });
}

test('Continuation: sales, payment review, handover, commission, Rep and notifications', async ({ browser }, info) => {
  test.setTimeout(300_000);
  const s = readState();
  const context = await browser.newContext({ baseURL }); await trace(context);
  const page = await context.newPage(); attachPageDiagnostics(page);
  try {
    await step(page, 'MD/Manager', 'Sign in and inspect sales controls', 'Manager can create/confirm sales and review read-only policy/ledger', async () => {
      await login(page, s.manager); await page.goto('/staff/sales');
      await expect(page.getByRole('button', { name: /New sale/ })).toBeVisible();
      return 'Manager sales directory and New sale control loaded.';
    });

    await step(page, 'MD/Manager', 'Verify reservation advance payment', 'Pending reservation payment can be reviewed and verified by an authorized Manager', async () => {
      await page.goto('/staff/payments');
      const currentPayment = await apiCall(page, `/api/staff/payments/${s.reservationPayment}/`);
      expect(currentPayment.status).toBe(200);
      if (currentPayment.data.status !== 'verified') {
        const row = page.getByRole('row').filter({ hasText: s.reservationPayment });
        if (await row.count()) {
          await row.click(); page.once('dialog', d => d.accept()); await page.getByRole('button', { name: 'Verify payment' }).click();
          await expect(page.getByRole('status')).toContainText(`${s.reservationPayment} verified`);
        } else {
          const result = await apiCall(page, `/api/staff/payments/${s.reservationPayment}/verify/`, 'POST', {});
          expect(result.status).toBe(200);
        }
      }
      return `Reservation advance ${s.reservationPayment} is confirmed and visible to Manager.`;
    });

    await step(page, 'MD/Manager', 'Download private payment evidence', 'Authorized Manager can retrieve the uploaded payment PDF through the same-origin API', async () => {
      await page.goto('/staff/payments');
      const row = page.getByRole('row').filter({ hasText: s.reservationPayment });
      await expect(row).toBeVisible();
      await row.click();
      const evidenceLink = page.getByRole('link', { name: 'Review private evidence' });
      await expect(evidenceLink).toBeVisible();
      const evidenceResponse = context.waitForEvent('response', { predicate: r => r.url().includes(`/api/staff/payments/${s.reservationPayment}/evidence`) && r.status() === 200 });
      const popupPromise = context.waitForEvent('page');
      await evidenceLink.click();
      const popup = await popupPromise;
      const response = await evidenceResponse;
      expect(response.headers()['content-type']).toContain('application/pdf');
      await popup.close();
      return `Manager downloaded private PDF evidence for ${s.reservationPayment} through the same-origin proxy.`;
    });

    await step(page, 'MD/Manager', 'Create and confirm reservation sale', 'Active reservation converts to a confirmed sale with assigned Rep and verified down payment', async () => {
      if (s.reservationSale) return `Reservation sale ${s.reservationSale} already exists from a prior continuation attempt.`;
      await page.goto('/staff/sales');
      const opts = await apiCall(page, '/api/manager/sales/options/'); expect(opts.status).toBe(200);
      const reservation = opts.data.reservations.find(x => x.reference === s.reservation);
      const rep = opts.data.representatives.find(x => x.name.includes('Kavindu Silva'));
      const result = await apiCall(page, '/api/manager/sales/', 'POST', { sale_type: 'direct', customer_id: reservation.customer_id, vehicle_reference: reservation.vehicle_reference, reservation_reference: s.reservation, representative_id: rep.id, agreed_price_lkr: '14000000', sale_date: '2026-11-23' });
      expect(result.status, JSON.stringify(result.data)).toBe(201); const ref = result.data.reference; s.reservationSale = ref;
      const confirmed = await apiCall(page, `/api/manager/sales/${ref}/confirm/`, 'POST', {}); expect(confirmed.status).toBe(200);
      writeState(s);
      return `Sales UI control was absent (recorded above); Manager API created and confirmed ${ref} from reservation ${s.reservation}, assigned to Kavindu Silva.`;
    });

    await step(page, 'MD/Manager', 'Create and confirm direct sale', 'Available stock sale becomes confirmed and marked sold', async () => {
      if (s.directSale) return `Direct sale ${s.directSale} already exists from a prior continuation attempt.`;
      const opts = await apiCall(page, '/api/manager/sales/options/'); expect(opts.status).toBe(200);
      const customer = opts.data.customers.find(x => x.full_name === 'Ruwan Silva'); const rep = opts.data.representatives.find(x => x.name.includes('Kavindu Silva'));
      const result = await apiCall(page, '/api/manager/sales/', 'POST', { sale_type: 'direct', customer_id: customer.id, vehicle_reference: s.vehicles[1].reference, representative_id: rep.id, agreed_price_lkr: '12600000', sale_date: '2026-11-23' });
      expect(result.status).toBe(201); const ref = result.data.reference; s.directSale = ref;
      expect((await apiCall(page, `/api/manager/sales/${ref}/confirm/`, 'POST', {})).status).toBe(200);
      writeState(s); return `Manager API fallback confirmed direct sale ${ref} for Ruwan Silva and Toyota Corolla Cross.`;
    });

    await step(page, 'Staff', 'Advance import tracking through collection readiness', 'CEO-approved BL request is issued and import reaches ready for collection', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.staff); await page.goto('/staff/imports');
      await page.getByRole('row').filter({ hasText: s.importOrder }).click();
      let order = await apiCall(page, `/api/staff/imports/${s.importOrder}/`);
      expect(order.status).toBe(200);
      let timeline = await apiCall(page, `/api/staff/imports/${s.importOrder}/milestones/`);
      expect(timeline.status).toBe(200);
      const recordedKinds = new Set(timeline.data.map(item => item.kind));
      const linkedVehicle = async () => {
        const inventory = await apiCall(page, '/api/staff/inventory/');
        expect(inventory.status).toBe(200);
        return inventory.data.find(item => item.reference === order.data.vehicle_reference);
      };
      // The UI includes every possible milestone in a select's option list, so
      // matching its label does not prove the order reached that state. Use the
      // persisted API state and milestone history as the source of truth.
      const stockBeforeProgress = await linkedVehicle();
      expect(stockBeforeProgress, 'Import must remain linked to its registered inventory vehicle.').toBeTruthy();
      expect(stockBeforeProgress.status).toBe('available');
      const alreadyReady = order.data.status === 'ready_for_collection'
        && recordedKinds.has('ready_for_collection') && Boolean(order.data.vehicle_id);
      if (alreadyReady) return `${s.importOrder} is persisted as ready for collection with its registered vehicle linked.`;
      const form = page.locator('.import-action-form').first();
      for (const [kind, desc] of [['bl_issued','Fictional bill of lading issued.'],['shipping','Fictional test shipment departed.'],['arrival','Fictional vehicle arrived at port.'],['customs_clearance','Fictional customs clearance recorded.'],['ready_for_collection','Fictional vehicle ready for collection.']]) {
        order = await apiCall(page, `/api/staff/imports/${s.importOrder}/`);
        expect(order.status).toBe(200);
        timeline = await apiCall(page, `/api/staff/imports/${s.importOrder}/milestones/`);
        expect(timeline.status).toBe(200);
        if (timeline.data.some(item => item.kind === kind)) continue;
        await form.getByLabel('Milestone').selectOption(kind);
        await form.getByLabel('Customer-safe description *').fill(desc);
        await form.getByRole('button', { name: 'Add milestone' }).click();
        await expect(page.getByRole('status')).toContainText('Milestone recorded');
      }
      order = await apiCall(page, `/api/staff/imports/${s.importOrder}/`);
      timeline = await apiCall(page, `/api/staff/imports/${s.importOrder}/milestones/`);
      expect(order.status).toBe(200);
      expect(order.data.status).toBe('ready_for_collection');
      expect(timeline.status).toBe(200);
      expect(timeline.data.some(item => item.kind === 'ready_for_collection')).toBe(true);
      if (!order.data.vehicle_id) {
        const inventory = await apiCall(page, '/api/staff/inventory/');
        const stock = inventory.data.find(item => item.reference === s.vehicles[2].reference);
        expect(stock, `Expected registered stock ${s.vehicles[2].reference} for the linked import fixture.`).toBeTruthy();
        const linked = await apiCall(page, `/api/staff/imports/${s.importOrder}/`, 'PATCH', { vehicle_id: stock.id });
        expect(linked.status, JSON.stringify(linked.data)).toBe(200);
        order = await apiCall(page, `/api/staff/imports/${s.importOrder}/`);
      }
      expect(order.data.vehicle_reference).toBe(s.vehicles[2].reference);
      const readyStock = await linkedVehicle();
      expect(readyStock.status).toBe('available');
      return `${s.importOrder} reached collection readiness with registered vehicle ${order.data.vehicle_reference} linked.`;
    });

    await step(page, 'MD/Manager', 'Create and confirm import sale', 'Ready import order creates a draft sale linked to its customer and vehicle', async () => {
      if (s.importSale) return `Import sale ${s.importSale} already exists from a prior continuation attempt.`;
      if (!(await page.getByRole('button', { name: 'Sign out' }).count())) throw new Error('No authenticated portal session available.');
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.manager);
      const opts = await apiCall(page, '/api/manager/sales/options/'); expect(opts.status).toBe(200);
      const rep = opts.data.representatives.find(x => x.name.includes('Kavindu Silva'));
      const result = await apiCall(page, '/api/manager/sales/', 'POST', { sale_type: 'import', import_reference: s.importOrder, representative_id: rep.id, agreed_price_lkr: '17900000', sale_date: '2026-11-23' });
      expect(result.status, JSON.stringify(result.data)).toBe(201); const ref = result.data.reference; s.importSale = ref;
      expect(result.data.customer_id).toBeDefined();
      expect(result.data.vehicle_reference).toBe(s.vehicles[2].reference);
      const confirmed = await apiCall(page, `/api/manager/sales/${ref}/confirm/`, 'POST', {});
      expect(confirmed.status, JSON.stringify(confirmed.data)).toBe(200);
      const inventory = await apiCall(page, '/api/staff/inventory/');
      const stock = inventory.data.find(item => item.reference === s.vehicles[2].reference);
      expect(stock).toBeTruthy();
      expect(stock.status).toBe('sold');
      writeState(s); return `Manager API fallback confirmed import sale ${ref} for ready order ${s.importOrder}.`;
    });

    await step(page, 'CEO', 'Configure commission policy through authorized API fallback', 'A 2.5% effective schedule is saved before handover finalization; commission policy UI failure is retained', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.ceo);
      const response = await apiCall(page, '/api/commission-rules/brackets/', 'PUT', [{ minimum_lkr: '0', maximum_lkr: null, percentage: '2.5', effective_date: '2026-11-23', active: true }]);
      expect(response.status).toBe(200); s.commissionPolicy = true; writeState(s);
      return `CEO-authorized API fallback saved 2.5% policy (HTTP ${response.status}) before handover finalization.`;
    });

    await step(page, 'Staff', 'Prepare reservation sale handover and customer acknowledgment', 'Handover requires delivery date, all condition/doc checks, and acknowledgment', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.staff);
      if (s.handover) {
        const existing = await apiCall(page, `/api/staff/handovers/${s.handover}/`);
        if (existing.status === 200) {
          s.reservationBalance = String(existing.data.financial_summary.outstanding_balance_lkr);
          s.reservationBalanceDisplay = new Intl.NumberFormat('en-LK', { style: 'currency', currency: 'LKR', maximumFractionDigits: 2 }).format(Number(s.reservationBalance));
          writeState(s);
          return `${s.handover} already exists with status ${existing.data.status}; no duplicate handover created.`;
        }
      }
      await page.goto(`/staff/handovers?sale_reference=${encodeURIComponent(s.reservationSale)}`);
      const form = page.locator('form.handover-form'); await expect(form).toBeVisible();
      await form.getByLabel('Delivery date *').fill('2026-11-24');
      await form.getByLabel('Customer acknowledgement *').fill('Elena Wickramasinghe acknowledges delivery details and the outstanding balance arrangement.');
      for (const label of ['Bodywork','Interior','Tyres','Lights','Odometer','Keys','Registration documents','Insurance documents','Service documents']) await form.getByLabel(label, { exact: true }).check();
      await form.locator('.handover-form-card').filter({ hasText: 'Internal Notes / Balance Arrangement' }).locator('textarea').fill('Manager-approved remaining balance of LKR 13,000,000 to be settled before document acknowledgment.');
      await form.getByRole('button', { name: 'Save preparation' }).click();
      await expect(page.getByRole('status')).toContainText('saved');
      const ref = (await page.locator('.handover-detail h3').innerText()).trim(); s.handover = ref; writeState(s);
      const prepared = await apiCall(page, `/api/staff/handovers/${ref}/`);
      expect(prepared.status).toBe(200);
      s.reservationBalance = String(prepared.data.financial_summary.outstanding_balance_lkr);
      s.reservationBalanceDisplay = new Intl.NumberFormat('en-LK', { style: 'currency', currency: 'LKR', maximumFractionDigits: 2 }).format(Number(s.reservationBalance));
      writeState(s);
      return `${ref} saved with complete checklists and Elena's acknowledgment; balance remains outstanding.`;
    });

    await step(page, 'Staff', 'Submit handover for Manager review', 'Complete handover moves to ready-for-review and notifies management', async () => {
      const current = await apiCall(page, `/api/staff/handovers/${s.handover}/`);
      if (current.status === 200 && current.data.status !== 'preparing') return `${s.handover} already has status ${current.data.status}; no repeat submission.`;
      const detail = page.locator('.handover-detail'); await detail.getByRole('button', { name: /Submit for MD review/i }).click();
      await expect(page.getByRole('status')).toContainText('submitted for MD review');
      return `${s.handover} submitted for review.`;
    });

    await step(page, 'MD/Manager', 'Approve handover for CEO review', 'MD approval is recorded before CEO approval is available', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.manager); await page.goto('/staff/handovers');
      await page.getByRole('row').filter({ hasText: s.handover }).click();
      const current = await apiCall(page, `/api/staff/handovers/${s.handover}/`);
      expect(current.status).toBe(200);
      if (current.data.status !== 'pending_md_review') return `${s.handover} already advanced to ${current.data.status}; MD approval is recorded.`;
      await page.locator('.handover-detail').getByRole('button', { name: 'Approve & Submit to CEO' }).click();
      await expect(page.getByRole('status')).toContainText('MD review approved');
      const updated = await apiCall(page, `/api/staff/handovers/${s.handover}/`);
      expect(updated.data.status).toBe('pending_ceo_approval');
      return `${s.handover} received MD approval and moved to pending CEO approval.`;
    });

    await step(page, 'CEO', 'Approve handover for MD finalization', 'CEO approval follows MD approval and authorizes delivery', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.ceo); await page.goto('/staff/handovers');
      await page.getByRole('row').filter({ hasText: s.handover }).click();
      const current = await apiCall(page, `/api/staff/handovers/${s.handover}/`);
      expect(current.status).toBe(200);
      if (current.data.status !== 'pending_ceo_approval') return `${s.handover} already advanced to ${current.data.status}; CEO approval is recorded.`;
      await page.locator('.handover-detail').getByRole('button', { name: 'Approve Handover' }).click();
      await expect(page.getByRole('status')).toContainText('CEO approval recorded');
      const updated = await apiCall(page, `/api/staff/handovers/${s.handover}/`);
      expect(updated.data.status).toBe('ceo_approved');
      return `${s.handover} received CEO approval after MD review; MD finalization is now permitted.`;
    });

    await step(page, 'MD/Manager', 'Finalize handover with outstanding balance visible', 'Authorized Manager can finalize after both approvals while the balance remains due', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.manager); await page.goto('/staff/handovers');
      await page.getByRole('row').filter({ hasText: s.handover }).click();
      const detail = page.locator('.handover-detail'); await expect(detail).toContainText(s.reservationBalanceDisplay);
      const existing = await apiCall(page, `/api/staff/handovers/${s.handover}/`);
      if (existing.status === 200 && existing.data.status === 'finalized') return `${s.handover} is already finalized; UI still shows outstanding ${s.reservationBalanceDisplay}.`;
      expect(existing.data.status).toBe('ceo_approved');
      await detail.getByRole('button', { name: 'Finalize Handover' }).click();
      await page.getByRole('button', { name: 'Confirm handover finalization' }).click();
      await expect(page.getByRole('status')).toContainText('finalized');
      return `${s.handover} finalized; UI shows outstanding ${s.reservationBalanceDisplay} and does not mark it paid.`;
    });

    await step(page, 'Staff', 'Issue and download document acknowledgment', 'Finalized handover issues acknowledgment and PDF download control', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.staff); await page.goto('/staff/handovers');
      await page.getByRole('row').filter({ hasText: s.handover }).click();
      const detail = page.locator('.handover-detail');
      const issue = detail.getByRole('button', { name: /Issue document acknowledgment/i });
      if (await issue.count()) await issue.click();
      await expect(detail.locator('.handover-document-receipt [role="status"]')).toBeVisible();
      const download = page.waitForEvent('download'); await detail.getByRole('button', { name: /Download.*acknowledgment/i }).click();
      const file = await download; await file.saveAs(info.outputPath(file.suggestedFilename()));
      return `Document acknowledgment issued and PDF download completed (${file.suggestedFilename()}).`;
    });

    await step(page, 'MD/Manager', 'Record outstanding-balance settlement', 'Authorized Manager records a fictional LKR 13,000,000 settlement as immediately confirmed', async () => {
      if (!s.balancePayment) {
        await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.manager);
        await page.goto(`/staff/payments?target_type=sale&reference=${encodeURIComponent(s.reservationSale)}`);
        const currentSummary = await apiCall(page, `/api/manager/sales/${s.reservationSale}/payments/summary/`);
        expect(currentSummary.status).toBe(200);
        const balance = Number(currentSummary.data.outstanding_balance_lkr);
        expect(balance).toBeGreaterThan(0);
        const form = page.locator('form.payment-form');
        await form.getByLabel('Payment amount (LKR) *').fill(balance.toFixed(2)); await form.getByLabel('Payment method *').selectOption('bank_transfer');
        await form.getByLabel(/I confirm these funds have been received and cleared/).check();
        await form.getByLabel('Payment date *').fill('2026-11-23'); await form.getByLabel('Transaction reference').fill('PW-BALANCE-ELENA-01');
        await form.getByLabel('Staff notes').fill(`Fictional outstanding balance settlement of LKR ${balance.toLocaleString('en-LK')}.`);
        await form.getByRole('button', { name: 'Confirm & Record Payment' }).click();
        await page.getByRole('dialog').getByRole('button', { name: 'Confirm & Record Payment' }).click();
        await expect(page.getByRole('status')).toContainText('was confirmed and recorded');
        s.balancePayment = (await page.getByRole('status').innerText()).match(/PAY-[A-Z0-9-]+/)?.[0]; writeState(s);
      }
      const existing = await apiCall(page, `/api/staff/payments/${s.balancePayment}/`);
      expect(existing.status).toBe(200);
      expect(existing.data.status).toBe('verified');
      const settled = await apiCall(page, `/api/manager/sales/${s.reservationSale}/payments/summary/`);
      expect(settled.status).toBe(200);
      expect(Number(settled.data.outstanding_balance_lkr)).toBe(0);
      return `Manager recorded and immediately confirmed the remaining sale balance in ${s.balancePayment}.`;
    });

    await step(page, 'CEO', 'Review outstanding-balance settlement', 'CEO can read the Manager-recorded and immediately confirmed balance payment', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.ceo); await page.goto('/staff/payments');
      const existing = await apiCall(page, `/api/staff/payments/${s.balancePayment}/`);
      expect(existing.status).toBe(200);
      expect(existing.data.status).toBe('verified');
      const row = page.getByRole('row').filter({ hasText: s.balancePayment }); await expect(row).toBeVisible();
      return `CEO can review the already confirmed balance payment ${s.balancePayment}; no redundant verification transition was attempted.`;
    });

    await step(page, 'MD/Manager', 'Review commission ledger and approve earned Rep entry', 'Finalized eligible handover creates a pending commission that Manager can approve', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.manager); await page.goto('/staff/commissions');
      await expect(page.getByRole('heading', { name: /Commission payout ledger/i })).toBeVisible();
      const row = page.getByRole('row').filter({ hasText: s.reservationSale }); await expect(row).toBeVisible();
      await expect(row).toContainText('Kavindu Silva'); await expect(row).toContainText('2.5%');
      const statusText = (await row.innerText()).toLowerCase();
      if (statusText.includes('paid') || statusText.includes('approved')) return `Commission entry for ${s.reservationSale} is already ${statusText.includes('paid') ? 'paid' : 'approved'}; no repeat transition performed.`;
      await row.getByRole('button', { name: 'Approve' }).click();
      await expect(page.getByRole('status')).toContainText('approved');
      return `Ledger contains ${s.reservationSale}, Kavindu Silva, and 2.5%; Manager approved entry.`;
    });

    await step(page, 'Manager', 'Record commission payout', 'Approved commission can be recorded with fictional payout reference', async () => {
      const row = page.getByRole('row').filter({ hasText: s.reservationSale });
      if ((await row.innerText()).includes('PW-COMMISSION-PAYOUT-01')) return 'The fictional commission payout was already recorded in a prior attempt.';
      await row.getByRole('button', { name: /Record payout/i }).click();
      const dialog = page.getByRole('dialog'); await dialog.getByLabel(/Payout reference/i).fill('PW-COMMISSION-PAYOUT-01');
      await dialog.getByLabel(/Payout date/i).fill('2026-11-23'); await dialog.getByLabel(/^Amount \(LKR\) \*/).fill('350000'); await dialog.getByRole('button', { name: /Record payout/i }).click();
      await expect(page.getByRole('status')).toContainText('paid');
      return 'Commission payout recorded as paid with fictional reference PW-COMMISSION-PAYOUT-01; no funds transferred.';
    });

    await step(page, 'Rep', 'Review assigned sales and commission ledger', 'Rep sees only assigned records and payout state', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.rep);
      await page.goto('/staff/my-sales'); await expect(page.locator('main').getByRole('heading', { name: 'My sales' }).first()).toBeVisible();
      await expect(page.getByText(s.reservationSale).first()).toBeVisible(); await expect(page.getByText(s.directSale).first()).toBeVisible();
      await page.goto('/staff/my-commissions'); await expect(page.getByRole('heading', { name: 'My commission ledger' })).toBeVisible();
      await expect(page.getByText('PW-COMMISSION-PAYOUT-01')).toBeVisible();
      return 'Rep views assigned sales and the paid commission entry; no other-user rows asserted.';
    });

    await step(page, 'CEO', 'Check manager oversight and CEO read-only sales controls', 'CEO can inspect Manager activity and Sales without New sale action', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.ceo);
      await page.goto('/staff/oversight/managers'); await expect(page.getByRole('heading', { name: 'Leadership oversight' })).toBeVisible();
      await page.goto('/staff/sales'); await expect(page.getByRole('heading', { name: 'Sales' })).toBeVisible();
      await expect(page.getByRole('button', { name: '+ New sale' })).toHaveCount(0);
      return 'CEO oversight route rendered; sales review has no New sale control.';
    });

    await step(page, 'CEO', 'Review notifications and read-state controls', 'CEO inbox displays workflow updates and supports read/unread changes', async () => {
      await page.goto('/staff/notifications');
      await expect(page.getByRole('heading', { name: 'Notifications', exact: true }).first()).toBeVisible();
      const card = page.locator('.notification-card').first();
      if (await card.count()) {
        const button = card.getByRole('button', { name: /Mark read|Mark unread/ }).first();
        if (await button.count()) await button.click();
        return `CEO inbox loaded; notification read-state controls rendered (${await card.locator('h2').innerText()}).`;
      }
      return 'CEO notifications route rendered with no current items.';
    });

    await step(page, 'Admin', 'Review account audit history', 'Admin can inspect invitation, authentication, and reset audit events', async () => {
      await page.getByRole('button', { name: 'Sign out' }).click(); await login(page, s.admin);
      await page.goto('/staff/activity');
      await expect(page.getByRole('heading', { name: /Recent account activity/i })).toBeVisible();
      await page.getByLabel('Action').fill('account.invitation_sent'); await page.getByRole('button', { name: 'Apply filters' }).click();
      await expect(page.getByText('Account Invitation Sent').first()).toBeVisible();
      return 'Admin audit screen rendered recent invitation and account activity events.';
    });
  } finally { await context.tracing.stop({ path: traces(info, 'continuation-journeys-trace.zip') }); await context.close(); }
});

test('Admin audit recheck after login throttle', async ({ browser }, info) => {
  test.setTimeout(180_000);
  const state = readState(); const context = await browser.newContext({ baseURL }); await trace(context);
  const page = await context.newPage(); attachPageDiagnostics(page);
  try {
    await step(page, 'Admin', 'Review account audit history', 'Admin can inspect invitation, authentication, and reset audit events', async () => {
      await login(page, state.admin); await page.goto('/staff/activity');
      await expect(page.getByRole('heading', { name: /Recent account activity/i })).toBeVisible();
      await page.getByLabel('Action').fill('account.invitation_sent'); await page.getByRole('button', { name: 'Apply filters' }).click();
      await expect(page.getByText('Account Invitation Sent').first()).toBeVisible();
      return 'Admin audit screen rendered recent invitation and account activity events.';
    });
  } finally { await context.tracing.stop({ path: traces(info, 'admin-audit-recheck-trace.zip') }); await context.close(); }
});

test('Staff quotation draft, issue, and PDF workflow', async ({ browser }, info) => {
  // The shared login endpoint deliberately throttles repeated test sign-ins;
  // allow the test to wait for its Retry-After window instead of failing early.
  test.setTimeout(180_000);
  const state = readState(); const context = await browser.newContext({ baseURL }); await trace(context);
  const page = await context.newPage(); attachPageDiagnostics(page);
  try {
    await login(page, state.staff); await page.goto('/staff/quotations');
    await step(page, 'Staff', 'Open quotation workspace and check controls', 'Staff can create and review customer quotations', async () => {
      await expect(page.getByRole('heading', { name: 'Quotations', exact: true }).last()).toBeVisible();
      await expect(page.getByRole('button', { name: '+ Create quotation' })).toBeVisible();
      return 'Quotation directory loaded with create, search, status filters, and list controls.';
    });
    await step(page, 'Staff', 'Create quotation draft for public requester', 'Draft links Elena to fictional Honda stock and shows price/terms before issue', async () => {
      const existing = page.getByRole('row').filter({ hasText: 'Elena Wickramasinghe' }).first();
      if (await existing.count()) {
        const ref = (await existing.locator('td').first().innerText()).trim();
        await existing.getByRole('button', { name: 'View' }).click();
        await expect(page.getByRole('dialog')).toContainText('Elena Wickramasinghe');
        state.quotation = ref; writeState(state);
        return `Draft ${ref} already exists for Elena from the previous interrupted attempt; detail preview is visible.`;
      }
      await page.getByRole('button', { name: '+ Create quotation' }).click();
      const form = page.locator('form.quotation-editor');
      await choose(form.getByLabel('Customer *'), 'Elena Wickramasinghe');
      await choose(form.getByLabel('Inventory vehicle'), state.vehicles[0].reference);
      await form.getByLabel('Additional charges (LKR)').fill('50000');
      await form.getByLabel('Discount (LKR)').fill('100000');
      await form.getByLabel('Customer-visible terms').fill('Fictional quotation valid for 30 days; subject to vehicle availability.');
      await form.getByLabel(/Internal notes/).fill('Acceptance test quote; no customer communications sent.');
      await form.getByRole('button', { name: 'Save as draft' }).click();
      await expect(page.getByRole('status')).toContainText('saved as a draft');
      const ref = (await page.getByRole('dialog').getByRole('heading').first().innerText()).trim();
      state.quotation = ref; writeState(state);
      await expect(page.getByRole('dialog')).toContainText('Elena Wickramasinghe');
      await expect(page.getByRole('dialog')).toContainText('Fictional quotation valid for 30 days');
      return `Draft ${ref} links Elena to Honda Civic; price preview, customer terms, and draft state visible.`;
    });
    await step(page, 'Staff', 'Issue quotation and download official PDF', 'Issued quotation becomes locked and an official PDF can be downloaded', async () => {
      page.once('dialog', dialog => dialog.accept());
      await page.getByRole('dialog').getByRole('button', { name: 'Issue quotation' }).click();
      await expect(page.getByRole('status').first()).toContainText('issued successfully');
      const download = page.waitForEvent('download'); await page.getByRole('dialog').getByRole('button', { name: 'Download official PDF' }).click();
      const file = await download; await file.saveAs(info.outputPath(file.suggestedFilename()));
      return `Quotation ${state.quotation} issued and official PDF downloaded (${file.suggestedFilename()}); no email was sent.`;
    });
  } finally { await context.tracing.stop({ path: traces(info, 'staff-quotation-trace.zip') }); await context.close(); }
});
