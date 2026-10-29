import { chromium } from 'playwright'
import fs from 'node:fs'
import assert from 'node:assert'

const state = {
  revision: 7, version: '3.0.0', role: 'developer',
  pack: { path: 'D:\\Games\\Minecraft\\PCL\\.minecraft\\versions\\1.20.1-Fabric', name: '1.20.1-Fabric', tacz: 'D:\\Games\\Minecraft\\PCL\\.minecraft\\versions\\1.20.1-Fabric\\tacz', loaded: true },
  presets: [
    { name: '默认枪包', version: 'v1.2.0', applied: true, count: 18, path: '' },
    { name: '轻量生存', version: 'v1.0.4', applied: false, count: 11, path: '' },
    { name: '竞技场', version: 'v2.1.0', applied: false, count: 24, path: '' },
    { name: '老版本备份', version: 'v0.9.2', applied: false, count: 8, path: '' },
  ],
  selected: '轻量生存',
  gunpacks: [
    { name: 'tacz_default_gun', type: 'folder', size: 0, file_count: 4 },
    { name: 'modern_warfare.zip', type: 'zip', size: 48213120, file_count: 132 },
    { name: 'm4_pack.zip', type: 'zip', size: 18210000, file_count: 48 },
    { name: 'pistols.zip', type: 'zip', size: 9210000, file_count: 31 },
  ],
  plan: { role: 'player', summary: '待下载 3 · 一致 9', counts: { download: 3, skip: 9 }, offline: false,
    items: [
      { path: 'modern_warfare.zip', name: 'modern_warfare.zip', action: 'download', label: '下载', size: 48213120, checked: true },
      { path: 'm4_pack.zip', name: 'm4_pack.zip', action: 'repair', label: '修复', size: 18210000, checked: true },
      { path: 'pistols.zip', name: 'pistols.zip', action: 'download', label: '下载', size: 9210000, checked: true },
      { path: 'old_pack.zip', name: 'old_pack.zip', action: 'ask_delete_local', label: '本地多余', size: 1200000, checked: false },
    ] },
  online: { available: true, account: { label: '186****9816', username: '18651999816', saved: true }, binding: { url: 'https://wwb.lanzouq.com/b01pulses', password: 'pulse', cloud_path: 'PulsesSwap/轻量生存', last_version: 'v1.0.4', history: [] } },
  settings: { storage_mode: 'isolated', role: 'developer', animations: true, online_sync_clean: true, online_auto_check: true, online_publish_preview: false, online_confirm_full: true },
  recent: [{ name: '1.20.1-Fabric', path: 'D:\\Games\\Minecraft\\PCL\\.minecraft\\versions\\1.20.1-Fabric' }],
  logs: [
    { time: '22:31:07', message: 'Pulses Swap v3.0.0 启动成功，作者: NimShade', level: 'SUCCESS', verbose: false },
    { time: '22:31:08', message: '数据库位置: D:\\PulsesSwap_database', level: 'INFO', verbose: true },
    { time: '22:31:09', message: '整合包已就绪: 1.20.1-Fabric · 预设 4 个', level: 'SUCCESS', verbose: false },
    { time: '22:31:12', message: '云端检查完成：待下载 3 · 一致 9', level: 'INFO', verbose: false },
  ],
  capabilities: { developer: true, online: true },
}

const browser = await chromium.launch({ executablePath: '/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] })
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 })
const errors = []
page.on('pageerror', e => errors.push(e.message))
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
await page.addInitScript((s) => {
  window.pywebview = { api: {
    async invoke() { return { ok: true, data: s } },
    async pick_folder() { return { ok: true, data: { path: s.pack.path } } },
    async handle_drop() { return { ok: true, data: {} } },
  } }
}, state)
await page.goto('http://127.0.0.1:8765/index.html', { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
fs.mkdirSync('/tmp/web_shots', { recursive: true })
await page.screenshot({ path: '/tmp/web_shots/01-home.png' })
assert.equal(await page.locator('h1').innerText(), '枪包预设')
const collapsed = await page.locator('.sidebar').evaluate(el => getComputedStyle(el).width)
assert.equal(collapsed, '60px')
assert.equal(await page.locator('.nav-item span').first().evaluate(el => getComputedStyle(el).display), 'none')

await page.locator('.sidebar').hover()
await page.waitForTimeout(550)
assert.equal(await page.locator('.sidebar').evaluate(el => getComputedStyle(el).width), '200px')
assert.equal(await page.locator('.app').evaluate(el => getComputedStyle(el).gridTemplateColumns.split(' ')[0]), '200px')
await page.screenshot({ path: '/tmp/web_shots/02-sidebar.png' })
await page.mouse.move(640, 450)
await page.waitForTimeout(500)

await page.locator('.nav-item').nth(2).click()
await page.waitForTimeout(310)
assert.ok(await page.locator('.cover').count())
await page.screenshot({ path: '/tmp/web_shots/03-cover.png' })
await page.waitForTimeout(1200)
assert.equal(await page.locator('h1').innerText(), '设置')
assert.equal(await page.locator('.cover').count(), 0)
await page.screenshot({ path: '/tmp/web_shots/05-settings.png' })

await page.locator('.tabs button').nth(1).click()
await page.waitForTimeout(200)
await page.screenshot({ path: '/tmp/web_shots/07-settings-db.png' })
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
assert.ok(overflow <= 1, `horizontal overflow ${overflow}`)

await page.locator('.nav-item').nth(3).click()
await page.waitForTimeout(1200)
assert.equal(await page.locator('h1').innerText(), '日志')
await page.screenshot({ path: '/tmp/web_shots/06-log.png' })

// DND overlay
await page.evaluate(() => {
  const dt = new DataTransfer()
  dt.items.add(new File(['x'], 'pack.zip'))
  window.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true, cancelable: true }))
})
await page.waitForTimeout(200)
assert.equal(await page.locator('.drop-overlay').count(), 1)
await page.screenshot({ path: '/tmp/web_shots/08-dnd.png' })
await page.evaluate(() => window.dispatchEvent(new DragEvent('dragleave', { bubbles: true })))
await page.waitForTimeout(100)

// responsive quick resize
for (const [w, h, name] of [[1140, 812, '09-1140x812'], [1600, 1000, '10-1600x1000']]) {
  await page.setViewportSize({ width: w, height: h })
  await page.waitForTimeout(300)
  const of = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  assert.ok(of <= 1, `${name} overflow ${of}`)
  await page.screenshot({ path: `/tmp/web_shots/${name}.png` })
}
assert.deepEqual(errors, [], JSON.stringify(errors))
await browser.close()
console.log('UI tests passed')
