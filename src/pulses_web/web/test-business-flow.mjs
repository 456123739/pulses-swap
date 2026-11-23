// Real built React -> HTTP -> Python Api/EventBus/JobRunner/Controller -> mock Lanzou HTTP.
// All account and ZIP data below are synthetic; no real account is used.
// Run: node src/pulses_web/web/test-business-flow.mjs (builds into a temporary directory).
import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn, spawnSync } from 'node:child_process'
import { once } from 'node:events'
import readline from 'node:readline'

const web = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(web, '../../..')
const output = path.join(root, 'docs/web-ui/verification')
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'pulses-ui-build-'))
const report = { synthetic: true, account: 'LOCAL MOCK ONLY — NOT A REAL ACCOUNT', steps: [] }
let server, browser, page
const pageErrors = []
async function waitFor(predicate, description, timeout = 120_000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    const value = await predicate()
    if (value) return value
    await new Promise(resolve => setTimeout(resolve, 80))
  }
  throw new Error(`Timed out: ${description}`)
}
try {
  fs.mkdirSync(output, { recursive: true })
  const build = spawnSync(process.execPath, ['node_modules/vite/bin/vite.js', 'build', '--outDir', temporary], { cwd: web, encoding: 'utf8' })
  assert.equal(build.status, 0, build.stderr || build.stdout)
  server = spawn(path.join(root, '.venv/bin/python'), ['tests/ui_bridge_server.py', '--dist', temporary], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] })
  let serverErrors = ''
  server.stderr.on('data', chunk => { serverErrors += chunk.toString() })
  const lines = readline.createInterface({ input: server.stdout })
  const url = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`Bridge startup timeout: ${serverErrors}`)), 20_000)
    lines.on('line', line => {
      try { const data = JSON.parse(line); if (data.url) { clearTimeout(timer); resolve(data.url) } } catch {}
    })
    server.once('exit', code => { clearTimeout(timer); reject(new Error(`Bridge exited ${code}: ${serverErrors}`)) })
  })
  const remote = async () => (await fetch(`${url}/__test/remote`)).json()
  const snapshot = async name => {
    await page.screenshot({ path: path.join(output, `business-flow-${name}-SIMULATED.png`), fullPage: true })
  }
  // Observe real job terminal events via the test-only read endpoint. Never invoke business operations here.
  const jobClick = async (method, click, expected = 'done') => {
    const before = await remote()
    const count = before.calls.filter(c => c.method === method).length
    await click()
    const call = await waitFor(async () => (await remote()).calls.filter(c => c.method === method)[count], method + ' UI submission')
    assert.ok(call.jobId, `${method} did not return a real jobId`)
    const event = await waitFor(async () => (await remote()).events.find(e => e.jobId === call.jobId), method + ' terminal event')
    if (event.type !== `job.${expected}`) {
      report.diagnostics = await remote()
      console.error(JSON.stringify(report.diagnostics, null, 2))
    }
    assert.equal(event.type, `job.${expected}`, JSON.stringify(event))
    await page.locator('.busy-toast').waitFor({ state: 'detached', timeout: 120_000 })
    report.steps.push({ operation: method, terminal: event.type })
    return event
  }
  browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] })
  page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })
  page.on('pageerror', error => pageErrors.push(error.message))
  // Guard against accidentally using a real external account/network endpoint.
  await page.route('**/*', route => {
    const target = new URL(route.request().url())
    return ['127.0.0.1', 'localhost'].includes(target.hostname) ? route.continue() : route.abort()
  })
  await page.goto(url)
  await page.getByRole('heading', { name: '枪包预设', exact: true }).waitFor()
  await jobClick('pack.open', () => page.locator('.next-step').getByRole('button').click())
  await snapshot('01-pack-open')
  await page.locator('.nav-item').nth(1).click()
  await page.getByRole('button', { name: '登录蓝奏', exact: true }).click()
  await page.getByLabel('蓝奏账号', { exact: true }).fill('123456')
  await page.getByLabel('密码', { exact: true }).fill('synthetic-ui-password')
  await page.locator('.modal-card button.primary').click()
  await page.locator('.modal-card').waitFor({ state: 'detached' })
  await page.locator('.sidebar').hover()
  await page.locator('.role-switch').click()
  await page.locator('.app.role-developer').waitFor()
  await page.locator('.cover').waitFor({ state: 'detached' })
  await page.locator('.nav-item').nth(0).click()
  await page.getByRole('button', { name: '新建', exact: true }).click()
  await page.locator('.modal-card input').fill('模拟界面预设')
  await page.locator('.modal-card button.primary').click()
  await page.locator('.detail-card h2', { hasText: '模拟界面预设' }).waitFor()
  await jobClick('preset.import', () => page.getByTestId('import-gunpacks').click())
  await page.locator('.gunpack-row', { hasText: 'alpha.zip' }).waitFor()
  await page.locator('.next-step').getByRole('button', { name: '上传到云端', exact: true }).click()
  await page.getByRole('dialog').waitFor()
  await page.getByLabel('云端文件夹', { exact: false }).fill('/PulsesSwap/UI-SIMULATED')
  await page.getByLabel('版本号', { exact: true }).fill('v2.3.4')
  await page.getByLabel('更新说明（可选）', { exact: true }).fill('模拟数据首发：alpha')
  await snapshot('02-first-upload-form')
  await jobClick('online.publish.new', () => page.locator('.modal-card button.primary').click())
  const first = await remote()
  assert.equal(first.manifests.length, 1)
  assert.equal(first.manifests[0].version, 'v2.3.4')
  assert.deepEqual(first.manifests[0].files.map(f => f.path), ['alpha.zip'])
  assert.equal(first.manifests[0].files[0].sha256, first.fixtures['alpha.zip'])
  assert.equal(first.files.find(f => f.name === (first.manifests[0].files[0].cloud || 'alpha.zip')).sha256, first.fixtures['alpha.zip'])
  assert.equal(first.manifests[0].notes, '模拟数据首发：alpha')
  assert.ok(Object.values(first.folders).some(f => f.name === 'UI-SIMULATED'))
  report.firstManifest = first.manifests[0]
  await snapshot('03-first-upload-done')
  await jobClick('preset.import', () => page.getByTestId('import-gunpacks').click())
  await page.locator('.gunpack-row', { hasText: 'beta.zip' }).waitFor()
  const updatesBefore = (await remote()).uploads.length
  await jobClick('online.publish.auto', () => page.getByTestId('one-click-upload').click())
  const second = await remote()
  assert.equal(second.manifests[0].version, 'v2.3.5')
  assert.deepEqual(second.manifests[0].files.map(f => f.path).sort(), ['alpha.zip', 'beta.zip'])
  for (const entry of second.manifests[0].files) {
    assert.equal(entry.sha256, second.fixtures[entry.path])
    assert.equal(second.files.find(f => f.name === (entry.cloud || entry.path)).sha256, second.fixtures[entry.path])
  }
  const incremental = second.uploads.slice(updatesBefore)
  assert.ok(incremental.includes(second.manifests[0].files.find(f => f.path === 'beta.zip').cloud || 'beta.zip'))
  assert.ok(!incremental.includes(first.manifests[0].files[0].cloud || 'alpha.zip'), 'Unchanged alpha must not be reuploaded')
  await page.locator('.detail-card').getByText('v2.3.5', { exact: true }).waitFor({ state: 'visible' })
  assert.equal(await page.locator('.detail-card').getByText('v2.3.5', { exact: true }).innerText(), 'v2.3.5')
  report.visiblePresetVersion = 'v2.3.5'
  report.secondManifest = second.manifests[0]
  report.incrementalUploads = incremental
  await snapshot('04-incremental-update')
  await jobClick('preset.import', () => page.getByTestId('import-gunpacks').click())
  const faultResponse = await fetch(`${url}/__test/break-manifest`, { method: 'POST' })
  assert.equal(faultResponse.status, 200)
  assert.equal((await faultResponse.json()).fault, 'manifest HTTP bytes corrupted')
  const beforeFailure = await remote()
  assert.equal(beforeFailure.cachedManifestVersion, 'v2.3.5', 'Scenario must retain a real historical manifest cache')
  const failure = await jobClick('online.publish.auto', () => page.getByTestId('one-click-upload').click(), 'error')
  const afterFailure = await remote()
  assert.deepEqual(afterFailure.files, beforeFailure.files, 'Manifest error must not mutate remote files')
  assert.deepEqual(afterFailure.uploads, beforeFailure.uploads, 'Manifest error must not upload using cached manifest')
  assert.deepEqual(afterFailure.deleted, beforeFailure.deleted)
  assert.equal(afterFailure.manifests[0].version, 'v2.3.5')
  assert.ok(!afterFailure.manifests[0].files.some(f => f.path === 'gamma.zip'))
  assert.ok(afterFailure.shareRequests.length > beforeFailure.shareRequests.length, 'Failure must attempt real share HTTP requests')
  report.cacheRejection = { error: failure.data.message, historicalCacheVersion: beforeFailure.cachedManifestVersion, unchangedRemote: true, version: afterFailure.manifests[0].version }
  await snapshot('05-manifest-error-no-cache')
  assert.deepEqual(pageErrors, [])
  const calls = afterFailure.calls.map(c => c.method)
  for (const method of ['account.login', 'app.role.switch', 'preset.create']) assert.ok(calls.includes(method), method)
  report.ok = true
  console.log(JSON.stringify({ ok: true, firstVersion: 'v2.3.4', secondVersion: 'v2.3.5', incrementalUploads: incremental, cacheRejection: report.cacheRejection }, null, 2))
} catch (error) {
  report.ok = false
  report.error = error.stack
  if (page) {
    await page.screenshot({ path: path.join(output, 'business-flow-FAILURE-SIMULATED.png'), fullPage: true }).catch(() => {})
    console.error((await page.locator('body').innerText().catch(() => '')).slice(0, 5000))
  }
  console.error(error)
  process.exitCode = 1
} finally {
  report.pageErrors = pageErrors
  fs.mkdirSync(output, { recursive: true })
  fs.writeFileSync(path.join(output, 'business-flow-SIMULATED-report.json'), JSON.stringify(report, null, 2))
  await browser?.close()
  if (server && server.exitCode === null) {
    const exited = once(server, 'exit')
    server.kill('SIGTERM')
    const timer = setTimeout(() => server.kill('SIGKILL'), 5000)
    await exited
    clearTimeout(timer)
  }
  // Only remove the exact mkdtemp directory created by this test.
  assert.ok(temporary.startsWith(path.join(os.tmpdir(), 'pulses-ui-build-')))
  fs.rmSync(temporary, { recursive: true, force: true })
}
