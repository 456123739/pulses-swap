import { chromium } from 'playwright'
import fs from 'node:fs'
import assert from 'node:assert'

const state = {
  revision: 7, version: '3.1.0', role: 'developer',
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
  plan: { role: 'developer', summary: '待上传 2 · 云端多余 1 · 一致 9', counts: { upload: 2, delete_cloud: 1, skip: 9 }, offline: false,
    items: [
      { path: 'modern_warfare.zip', name: 'modern_warfare.zip', action: 'upload', label: '上传', size: 48213120, checked: true },
      { path: 'm4_pack.zip', name: 'm4_pack.zip', action: 'upload', label: '上传', size: 18210000, checked: true },
      { path: 'pistols.zip', name: 'pistols.zip', action: 'delete_cloud', label: '删除云端', size: 9210000, checked: false },
      { path: 'old_pack.zip', name: 'old_pack.zip', action: 'skip', label: '一致', size: 1200000, checked: false },
    ] },
  online: { available: true, bound: ['轻量生存', '默认枪包'], bound_count: 2, account: { label: '186****9816', username: '18651999816', saved: true }, binding: { url: 'https://wwb.lanzouq.com/b01pulses', password: 'pulse', cloud_path: 'PulsesSwap/轻量生存', last_version: 'v1.0.4', history: [] } },
  settings: { storage_mode: 'isolated', role: 'developer', animations: true, online_sync_clean: true, online_auto_check: true, online_publish_preview: false, advanced_actions: false, online_confirm_full: true },
  recent: [{ name: '1.20.1-Fabric', path: 'D:\\Games\\Minecraft\\PCL\\.minecraft\\versions\\1.20.1-Fabric' }],
  logs: [
    { time: '22:31:07', message: 'Pulses Swap v3.1.0 启动成功，作者: NimShade', level: 'SUCCESS', verbose: false },
    { time: '22:31:08', message: '数据库位置: D:\\PulsesSwap_database', level: 'INFO', verbose: true },
    { time: '22:31:09', message: '整合包已就绪: 1.20.1-Fabric · 预设 4 个', level: 'SUCCESS', verbose: false },
    { time: '22:31:12', message: '云端检查完成：待下载 3 · 一致 9', level: 'INFO', verbose: false },
  ],
  capabilities: { developer: true, online: true },
}

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
  || '/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch({
  ...(executablePath && fs.existsSync(executablePath) ? { executablePath } : {}),
  args: ['--no-sandbox'],
})
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 1 })
const errors = []
page.on('pageerror', e => errors.push(e.message))
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
await page.addInitScript((s) => {
  window.__invokes = []
  window.pywebview = { api: {
    async invoke(method, params) {
      window.__invokes.push([method, params])
      if (method === 'app.role.switch') {
        s.role = params.role
        s.settings.role = params.role
        s.plan = params.role === 'player'
          ? { role: 'player', summary: '待下载 3 · 一致 9', items: [
              { path: 'modern_warfare.zip', name: 'modern_warfare.zip', action: 'download', label: '下载', size: 48213120, checked: true },
              { path: 'm4_pack.zip', name: 'm4_pack.zip', action: 'repair', label: '修复', size: 18210000, checked: true },
              { path: 'pistols.zip', name: 'pistols.zip', action: 'download', label: '下载', size: 9210000, checked: true },
              { path: 'old_pack.zip', name: 'old_pack.zip', action: 'ask_delete_local', label: '本地多余', size: 1200000, checked: false },
            ] }
          : { role: 'developer', summary: '待上传 2 · 云端多余 1 · 一致 9', items: [
              { path: 'modern_warfare.zip', name: 'modern_warfare.zip', action: 'upload', label: '上传', size: 48213120, checked: true },
              { path: 'm4_pack.zip', name: 'm4_pack.zip', action: 'upload', label: '上传', size: 18210000, checked: true },
              { path: 'pistols.zip', name: 'pistols.zip', action: 'delete_cloud', label: '删除云端', size: 9210000, checked: false },
              { path: 'old_pack.zip', name: 'old_pack.zip', action: 'skip', label: '一致', size: 1200000, checked: false },
            ] }
      } else if (method === 'app.settings.update') {
        Object.assign(s.settings, params)
      } else if (method === 'online.sync.all' || method === 'online.publish.all') {
        window.__autoMethod = method
        return { ok: true, data: { jobId: 'j_auto', cancelable: true } }
      } else if (method === 'preset.select') {
        s.selected = params.name
      }
      return { ok: true, data: JSON.parse(JSON.stringify(s)) }
    },
    async pick_folder() { return { ok: true, data: { path: s.pack.path } } },
    async handle_drop() { return { ok: true, data: {} } },
  } }
}, state)
await page.goto('http://127.0.0.1:8765/index.html', { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
fs.mkdirSync('/tmp/web_shots', { recursive: true })
await page.screenshot({ path: '/tmp/web_shots/01-home.png' })
assert.equal(await page.locator('h1').innerText(), '枪包预设')
// 主操作必须足够大、在首屏内，且是页面最显眼的动作
const primary = page.locator('.hero-primary')
const primaryBox = await primary.boundingBox()
assert.ok(primaryBox, '缺少一键替换主按钮')
assert.ok(primaryBox.height >= 52, `一键替换按钮高度 ${primaryBox.height}`)
assert.ok(primaryBox.width >= 190, `一键替换按钮宽度 ${primaryBox.width}`)
assert.equal((await primary.innerText()).trim(), '一键替换')
assert.ok(primaryBox.y + primaryBox.height <= 812, `主按钮不在首屏 ${primaryBox.y}`)
const secondaryBox = await page.locator('.hero-secondary').boundingBox()
assert.ok(secondaryBox.height >= 40, `次要按钮高度 ${secondaryBox.height}`)
assert.ok(primaryBox.height > secondaryBox.height, '主按钮没有比次要按钮更突出')
// 选预设后，枪包列表逐项滑入，且详情跟随切换
await page.locator('.preset-row').nth(2).click()
await page.waitForTimeout(520)
assert.equal((await page.locator('.detail-card h2').innerText()).trim(), '竞技场')
assert.equal(await page.locator('.gunpack-row').count(), 4)
const firstGunOpacity = await page.locator('.gunpack-row').first().evaluate(el => Number(getComputedStyle(el).opacity))
assert.ok(firstGunOpacity > 0.9, `枪包行未完成滑入 ${firstGunOpacity}`)
await page.locator('.preset-row').nth(1).click()
await page.waitForTimeout(520)
assert.equal((await page.locator('.detail-card h2').innerText()).trim(), '轻量生存')
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
const cover = page.locator('.cover')
const coverBox = await cover.boundingBox()
assert.ok(coverBox.width >= 1279 && coverBox.height >= 899, '幕布没有覆盖整个窗口')
assert.equal(await cover.evaluate(el => getComputedStyle(el).position), 'fixed')
assert.equal(await cover.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(242, 243, 245)')
const wordmarkColor = await cover.locator('.wordmark-pulses').evaluate(el => getComputedStyle(el).color)
assert.notEqual(wordmarkColor, 'rgb(255, 255, 255)', '幕布文字仍是白色')
assert.ok((await cover.locator('.cover-kicker').innerText()).includes('设置'))
await page.screenshot({ path: '/tmp/web_shots/03-cover.png' })
await page.waitForTimeout(1200)
assert.equal(await page.locator('h1').innerText(), '设置')
assert.equal(await page.locator('.cover').count(), 0)
await page.screenshot({ path: '/tmp/web_shots/05-settings.png' })

// 身份切换也必须使用浅色全窗幕布，并在结束后落到新身份
await page.getByRole('button', { name: '玩家', exact: true }).click()
await page.waitForTimeout(120)
assert.ok(await page.locator('.cover').count(), '身份切换没有幕布')
assert.ok((await page.locator('.cover-kicker').innerText()).includes('切换为玩家'))
assert.equal(await page.locator('.cover').evaluate(el => getComputedStyle(el).position), 'fixed')
await page.screenshot({ path: '/tmp/web_shots/11-role-cover.png' })
await page.waitForTimeout(1400)
assert.equal(await page.locator('.cover').count(), 0)
assert.ok(await page.locator('.app.role-player').count(), '身份没有切换为玩家')
assert.equal(await page.locator('.sidebar-foot').innerText(), '玩家')
// 玩家管理页：默认一键更新，不需要勾选
await page.locator('.nav-item').nth(1).click()
await page.waitForTimeout(1200)
assert.equal((await page.locator('.manage-action .action-primary').innerText()).trim(), '一键更新全部')
assert.ok((await page.locator('.plan-card .pill').innerText()).includes('待下载'))
assert.equal(await page.locator('.plan-card input[type=checkbox]').count(), 0, '玩家默认模式仍有差异勾选框')
await page.screenshot({ path: '/tmp/web_shots/12-player-manage.png' })
await page.locator('.manage-action .action-primary').click()
await page.waitForTimeout(120)
assert.equal(await page.evaluate(() => window.__autoMethod), 'online.sync.all')
await page.evaluate(() => window.PS.push({ type: 'job.done', jobId: 'j_auto', data: { result: { message: '一键更新完成', state: null } } }))
await page.waitForTimeout(120)
// 切回开发者，保持后续截图一致
await page.getByRole('button', { name: '切换为开发者', exact: true }).click()
await page.waitForTimeout(1400)
assert.ok(await page.locator('.app.role-developer').count())
await page.locator('.nav-item').nth(2).click()
await page.waitForTimeout(1200)

await page.locator('.tabs button').nth(1).click()
await page.waitForTimeout(200)
await page.screenshot({ path: '/tmp/web_shots/07-settings-db.png' })
const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
assert.ok(overflow <= 1, `horizontal overflow ${overflow}`)

await page.locator('.nav-item').nth(3).click()
await page.waitForTimeout(1200)
assert.equal(await page.locator('h1').innerText(), '日志')
await page.screenshot({ path: '/tmp/web_shots/06-log.png' })

// 1140 最小窗口：首页主操作仍要在首屏且不横向溢出
await page.setViewportSize({ width: 1140, height: 812 })
await page.locator('.nav-item').nth(0).click()
await page.waitForTimeout(1200)
assert.equal(await page.locator('h1').innerText(), '枪包预设')
const narrowPrimary = await page.locator('.hero-primary').boundingBox()
assert.ok(narrowPrimary, '1140 下缺少主按钮')
assert.ok(narrowPrimary.y + narrowPrimary.height <= 812, '1140 下主按钮不在首屏')
assert.ok(narrowPrimary.x + narrowPrimary.width <= 1140 - 8, `1140 下主按钮横向溢出 ${narrowPrimary.x + narrowPrimary.width}`)
const narrowOverflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
assert.ok(narrowOverflow <= 1, `1140 横向溢出 ${narrowOverflow}`)
await page.screenshot({ path: '/tmp/web_shots/09-1140x812.png' })

// 管理页主操作条同样要大且可见
await page.locator('.nav-item').nth(1).click()
await page.waitForTimeout(1200)
const managePrimary = page.locator('.manage-action .action-primary')
const manageBox = await managePrimary.boundingBox()
assert.ok(manageBox, '管理页缺少主操作')
assert.ok(manageBox.height >= 46, `管理页主操作高度 ${manageBox.height}`)
assert.ok(manageBox.y + manageBox.height <= 812, '管理页主操作不在首屏')
assert.equal((await managePrimary.innerText()).trim(), '一键上传全部')
assert.ok((await page.locator('.plan-card .pill').innerText()).includes('待上传'))
assert.equal(await page.getByText('待下载', { exact: false }).count(), 0, '开发者页出现待下载')
assert.equal(await page.locator('.plan-card input[type=checkbox]').count(), 0, '默认模式仍有勾选框')
assert.equal(await page.locator('.publish-row').count(), 0, '默认模式仍有版本号表单')
await page.screenshot({ path: '/tmp/web_shots/10-manage-1140.png' })
// 主按钮必须真的调用“一键上传全部”
await managePrimary.click()
await page.waitForTimeout(120)
assert.equal(await page.evaluate(() => window.__autoMethod), 'online.publish.all')
await page.evaluate(() => window.PS.push({ type: 'job.done', jobId: 'j_auto', data: { result: { message: '一键上传完成', state: null } } }))
await page.waitForTimeout(120)
assert.equal(await page.locator('.busy-toast').count(), 0)
await page.setViewportSize({ width: 1280, height: 900 })
await page.locator('.nav-item').nth(0).click()
await page.waitForTimeout(1200)

// 主按钮确认弹窗可 Esc 关闭，不应重复提交
await page.locator('.hero-primary').click()
await page.waitForTimeout(120)
assert.equal(await page.locator('.modal-card').count(), 1)
assert.ok(await page.locator('.modal-card').evaluate(el => el.contains(document.activeElement)), '弹窗没有接管焦点')
await page.keyboard.press('Tab')
assert.ok(await page.locator('.modal-card').evaluate(el => el.contains(document.activeElement)), 'Tab 焦点跑出弹窗')
await page.keyboard.press('Escape')
await page.waitForTimeout(100)
assert.equal(await page.locator('.modal-card').count(), 0)
assert.ok(await page.locator('.hero-primary').evaluate(el => el === document.activeElement), '关闭弹窗后没有归还焦点')

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
// drop 必须收起遮罩，不能留下永久覆盖层
await page.evaluate(() => {
  const dt = new DataTransfer()
  dt.items.add(new File(['x'], 'pack.zip'))
  window.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true, cancelable: true }))
  window.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }))
})
await page.waitForTimeout(120)
assert.equal(await page.locator('.drop-overlay').count(), 0, 'drop 后遮罩仍在')

// responsive quick resize
for (const [w, h, name] of [[1140, 812, '09-1140x812'], [1600, 1000, '10-1600x1000']]) {
  await page.setViewportSize({ width: w, height: h })
  await page.waitForTimeout(300)
  const of = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)
  assert.ok(of <= 1, `${name} overflow ${of}`)
  await page.screenshot({ path: `/tmp/web_shots/${name}.png` })
}
// 高级操作默认关闭；开启后才出现版本号/勾选
await page.locator('.nav-item').nth(2).click()
await page.waitForTimeout(1200)
const advancedSwitch = page.getByRole('switch', { name: '高级操作' })
assert.equal(await advancedSwitch.getAttribute('aria-checked'), 'false')
await advancedSwitch.click()
await page.waitForTimeout(200)
await page.locator('.nav-item').nth(1).click()
await page.waitForTimeout(1200)
assert.equal(await page.locator('.publish-row').count(), 1, '高级模式缺少版本号表单')
assert.ok(await page.locator('.plan-card input[type=checkbox]').count() >= 4, '高级模式缺少差异勾选')
await page.screenshot({ path: '/tmp/web_shots/13-developer-advanced.png' })
await page.locator('.nav-item').nth(2).click()
await page.waitForTimeout(1200)
await page.getByRole('switch', { name: '高级操作' }).click()
await page.waitForTimeout(200)

// 关闭动画后切页应一帧到位，不应再出现幕布
await page.locator('.nav-item').nth(2).click()
await page.waitForTimeout(1200)
await page.locator('.settings-page .switch').first().click()
await page.waitForTimeout(150)
await page.locator('.nav-item').nth(3).click()
await page.waitForTimeout(60)
assert.equal(await page.locator('.cover').count(), 0, '关闭动画后仍出现幕布')
assert.equal(await page.locator('h1').innerText(), '日志')
assert.deepEqual(errors, [], JSON.stringify(errors))
await browser.close()
console.log('UI tests passed')
