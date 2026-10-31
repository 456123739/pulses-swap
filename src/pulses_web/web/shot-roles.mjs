import { chromium } from 'playwright'
import fs from 'node:fs'

const base = {
  revision: 9, version: '3.1.3', role: 'player',
  pack: {
    path: 'D:\\Games\\Minecraft\\PCL\\.minecraft\\versions\\1.20.1-Fabric',
    name: '1.20.1-Fabric',
    tacz: 'D:\\Games\\Minecraft\\PCL\\.minecraft\\versions\\1.20.1-Fabric\\tacz',
    loaded: true,
  },
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
  plan: {
    role: 'player', summary: '待下载 3 · 一致 9',
    counts: { download: 3, skip: 9 }, offline: false,
    items: [
      { path: 'modern_warfare.zip', name: 'modern_warfare.zip', action: 'download', label: '下载', size: 48213120, checked: true },
      { path: 'm4_pack.zip', name: 'm4_pack.zip', action: 'repair', label: '修复', size: 18210000, checked: true },
      { path: 'pistols.zip', name: 'pistols.zip', action: 'download', label: '下载', size: 9210000, checked: true },
      { path: 'old_pack.zip', name: 'old_pack.zip', action: 'ask_delete_local', label: '本地多余', size: 1200000, checked: false },
    ],
  },
  publish_ready: false,
  online: {
    available: true,
    bound: ['轻量生存', '默认枪包'],
    bound_count: 2,
    account: { label: '186****9816', username: '18651999816', saved: true },
    binding: {
      url: 'https://wwb.lanzouq.com/b01pulses', password: 'pulse',
      cloud_path: 'PulsesSwap/轻量生存', last_version: 'v1.0.4', history: [],
    },
  },
  settings: {
    storage_mode: 'isolated', role: 'player', animations: true,
    online_sync_clean: true, online_auto_check: true,
    online_publish_preview: false, online_confirm_full: true,
  },
  recent: [{ name: '1.20.1-Fabric', path: 'D:\\Games\\Minecraft\\PCL\\.minecraft\\versions\\1.20.1-Fabric' }],
  logs: [
    { time: '21:57:07', message: 'Pulses Swap v3.1.3 启动成功，作者: NimShade', level: 'SUCCESS', verbose: false },
    { time: '21:57:08', message: '整合包已就绪: 1.20.1-Fabric · 预设 4 个', level: 'SUCCESS', verbose: false },
    { time: '21:57:12', message: '云端检查完成：待下载 3 · 一致 9', level: 'INFO', verbose: false },
  ],
  capabilities: { developer: true, online: true },
}

const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
    || '/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',
  args: ['--no-sandbox'],
})
fs.mkdirSync('/tmp/role_shots', { recursive: true })
fs.mkdirSync('/home/admin/111/pulses-swap/docs/web-ui/roles', { recursive: true })

async function shot(role) {
  const state = JSON.parse(JSON.stringify(base))
  state.role = role
  state.settings.role = role
  state.publish_ready = role === 'developer'
  state.plan = role === 'developer'
    ? { role: 'developer', summary: '待上传 2 · 云端多余 1 · 一致 9', offline: false,
        items: [
          { path: 'modern_warfare.zip', name: 'modern_warfare.zip', action: 'upload', label: '上传', size: 48213120, checked: true },
          { path: 'm4_pack.zip', name: 'm4_pack.zip', action: 'upload', label: '上传', size: 18210000, checked: true },
          { path: 'pistols.zip', name: 'pistols.zip', action: 'delete_cloud', label: '删除云端', size: 9210000, checked: false },
          { path: 'old_pack.zip', name: 'old_pack.zip', action: 'skip', label: '一致', size: 1200000, checked: false },
        ] }
    : { role: 'player', summary: '待下载 3 · 一致 9', offline: false,
        items: [
          { path: 'modern_warfare.zip', name: 'modern_warfare.zip', action: 'download', label: '下载', size: 48213120, checked: true },
          { path: 'm4_pack.zip', name: 'm4_pack.zip', action: 'repair', label: '修复', size: 18210000, checked: true },
          { path: 'pistols.zip', name: 'pistols.zip', action: 'download', label: '下载', size: 9210000, checked: true },
          { path: 'old_pack.zip', name: 'old_pack.zip', action: 'ask_delete_local', label: '本地多余', size: 1200000, checked: false },
        ] }
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 })
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  await page.addInitScript((s) => {
    window.pywebview = { api: {
      async invoke() { return { ok: true, data: JSON.parse(JSON.stringify(s)) } },
      async pick_folder() { return { ok: true, data: { path: s.pack.path } } },
      async handle_drop() { return { ok: true, data: {} } },
    } }
  }, state)
  await page.goto('http://127.0.0.1:8765/index.html', { waitUntil: 'networkidle' })
  await page.waitForTimeout(650)
  await page.screenshot({ path: `/tmp/role_shots/${role}-home.png` })
  await page.locator('.nav-item').nth(1).click()
  await page.waitForTimeout(1300)
  await page.screenshot({ path: `/tmp/role_shots/${role}-manage.png` })
  await page.locator('.nav-item').nth(2).click()
  await page.waitForTimeout(1300)
  await page.screenshot({ path: `/tmp/role_shots/${role}-settings.png` })
  if (errors.length) throw new Error(`${role} console errors: ${errors.join('; ')}`)
  await page.close()
}

await shot('player')
await shot('developer')
await browser.close()
console.log('role screenshots done')
