const {createRequire} = require('node:module');
const {chromium} = createRequire(process.env.PR206_PLAYWRIGHT_ROOT + '/package.json')('playwright');
const root = 'https://gateway-pr200-pr206-ui.up.railway.app/field/';
const output = 'C:/Users/ACER/AppData/Local/Temp/opencode/pr206-ui-20261128/';
const trip = 'TRIP-ACC-20261128-01';
const first = 'WH/OUT/06409', second = 'WH/OUT/06410';
const expectedUuid = '3038c01a-433c-4c8f-9a5d-95c63abc61be';
const office = {latitude:1.487,longitude:124.8428,accuracy:2};

(async () => {
  const browser = await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
  const context = await browser.newContext({viewport:{width:390,height:844},geolocation:office,permissions:['geolocation']});
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  const snapshots = [], commands = [];
  page.on('request', r => {
    if (new URL(r.url()).pathname !== '/api/v1/sync/commands') return;
    const body = r.postDataJSON();
    commands.push({type: body?.type, uuid: body?.client_uuid});
    console.log('COMMAND_REQUEST', JSON.stringify(commands.at(-1)));
  });
  page.on('response', async r => {
    const path = new URL(r.url()).pathname;
    if (path === '/api/v1/sync/snapshot' && r.ok()) {
      const s = await r.json();
      const row = {
        status: r.status(),
        scope: s.scope,
        pairs: (s.deliveries || []).map(d => [d.id, d.outlet_id]),
        accepted: s.accepted_delivery_pods || {},
        trips: (s.deliveries || []).map(d => d.trip),
      };
      snapshots.push(row);
      console.log('SNAPSHOT', JSON.stringify(row));
    }
  });
  try {
    await page.goto(root, {waitUntil:'domcontentloaded', timeout:45000});
    await page.getByLabel('Nama pengguna').waitFor({timeout:45000});
    await page.getByLabel('Nama pengguna').fill('driver-01');
    await page.getByLabel('Kata sandi').fill(process.env.PR206_DRIVER_PW);
    await page.getByRole('button', {name:'Masuk', exact:true}).click();
    await page.getByRole('button', {name:'Delivery', exact:true}).waitFor({timeout:45000});

    // Attendance state is local-only in this PWA, so a fresh device repeats the
    // morning flow. This writes attendance only; it never submits a POD or closing.
    if (!await page.locator('[data-testid="attendance-record"]').isVisible()) {
      await page.getByRole('button', {name:'Absen masuk', exact:true}).first().click();
      await page.getByRole('button', {name:'Perbarui lokasi', exact:true}).click();
      await page.getByLabel('Alamat / nama lokasi').fill('Kantor MDU [fork disposable retest]');
      await page.getByRole('button', {name:'Ambil selfie', exact:true}).click();
      await page.getByLabel('Buka Kamera Perangkat').setInputFiles(process.env.PR206_PLAYWRIGHT_ROOT + '/public/icon-192.png');
      await page.getByRole('button', {name:'Gunakan foto', exact:true}).click();
      await page.getByAltText('Foto absensi dengan watermark').waitFor();
      await page.getByRole('region', {name:'Absensi foto dan lokasi'}).getByRole('button', {name:'Absen masuk', exact:true}).click();
      await page.locator('[data-testid="attendance-record"]').waitFor({timeout:45000});
      console.log('MORNING_ATTENDANCE_REPEATED_LOCAL_ONLY', JSON.stringify({note:'fresh device, attendance only'}));
    }
    const sync = page.getByRole('button', {name:'Sinkronkan data harian', exact:true});
    if (await sync.isVisible()) await sync.click();
    await page.getByText('Sesi aktif', {exact:true}).waitFor({timeout:45000});
    await page.getByRole('button', {name:'Delivery', exact:true}).click();
    await page.getByRole('button', {name:/^Buka TRIP/}).waitFor({timeout:45000});

    const listText = await page.locator('body').innerText();
    const listProgress = listText.match(/([0-9])\/2 toko selesai/)?.[1];
    console.log('TRIP_LIST', JSON.stringify({progress:listProgress, body:listText.slice(0,700)}));
    await page.screenshot({path: output + '03-new-context-progress-1-of-2-list.png', fullPage:true});
    console.log('SCREENSHOT 03-new-context-progress-1-of-2-list.png');

    await page.getByRole('button', {name:/^Buka TRIP/}).click();
    const region = page.getByRole('region', {name:/^Daftar toko /});
    await region.getByRole('button', {name:'Buka '+first, exact:true}).waitFor();
    const firstCard = await region.locator('.ui-card').filter({hasText:first}).innerText();
    const secondCard = await region.locator('.ui-card').filter({hasText:second}).innerText();
    const body = await page.locator('body').innerText();
    const progress = body.match(/([0-9])\/2 toko selesai/)?.[1];
    const tripOpen = body.includes('Belum ditutup');
    const accepted = snapshots.at(-1)?.accepted || {};
    console.log('RESTORATION', JSON.stringify({
      progress, tripOpen, accepted, expectedUuid,
      firstCard, secondCard, commandRequests: commands,
    }));
    await page.screenshot({path: output + '03-new-context-progress-1-of-2.png', fullPage:true});
    console.log('SCREENSHOT 03-new-context-progress-1-of-2.png');

    if (progress !== '1') throw new Error('Expected 1/2, got ' + progress + '/2');
    if (accepted[first] !== expectedUuid) throw new Error('Snapshot did not return first POD receipt: ' + JSON.stringify(accepted));
    if (accepted[second]) throw new Error('Second DO unexpectedly has a POD');
    if (!firstCard.includes('Selesai')) throw new Error('First card not completed: ' + firstCard);
    if (secondCard.includes('Selesai')) throw new Error('Second card unexpectedly completed: ' + secondCard);
    if (!tripOpen) throw new Error('Trip is not open');
    if (commands.length) throw new Error('Verification posted delivery commands: ' + JSON.stringify(commands));
    console.log('RESTORATION_PASS', JSON.stringify({trip, first, second, receipt:accepted[first], progress:'1/2'}));
  } catch (err) {
    console.error('RESTORATION_FAIL', String(err));
    await page.screenshot({path: output + 'restoration-failure.png', fullPage:true}).catch(()=>{});
    process.exitCode = 1;
  } finally {
    await context.close();
    await browser.close();
  }
})().catch(err => { console.error('FATAL', String(err)); process.exitCode = 1; });
