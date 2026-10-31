import { chromium } from 'playwright'
import fs from 'node:fs'

const base = {
  revision: 1, version: '3.1.1', role: 'developer',
  pack: { path: 'D:\\Games\\Minecraft\\PCL\\.minecraft\\versions\\1.20.1-Fabric', name: '1.20.1-Fabric', tacz: 'x', loaded: true },
  presets: [{ name: '轻量生存', version: 'v1.0.4', applied: false, count: 11, path: '' }],
  selected: '轻量生存', gunpacks: [{ name: 'a.zip', type: 'zip' }],
  plan: { role: 'developer', summary: '待上传 1 · 一致 9', items: [{ path: 'a.zip', name: 'a.zip', action: 'upload', label: '上传', checked: true }] },
  publish_ready: false,
  online: {
    available: true, bound: ['轻量生存'], bound_count: 1,
    account: { label: '186****9816' },
    binding: { url: 'https://wwb.lanzouq.com/b01pulses', password: 'pulse', cloud_path: 'PulsesSwap/轻量生存', history: [] },
  },
  settings: { storage_mode: 'isolated', role: 'developer', animations: false, advanced_actions: false, online_sync_clean: true, online_auto_check: true, online_confirm_full: true },
  recent: [], logs: [], capabilities: { developer: true, online: true },
}

const executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
  || '/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch({
  ...(fs.existsSync(executablePath) ? { executablePath } : {}),
  args: ['--no-sandbox'],
})
const failures = []
for (const advanced of [false, true]) {
  for (const [w, h] of [[1280, 900], [1140, 812]]) {
    const state = JSON.parse(JSON.stringify(base))
    state.settings.advanced_actions = advanced
    const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 1 })
    await page.addInitScript((s) => {
      window.pywebview = { api: {
        async invoke() { return { ok: true, data: s } },
        async pick_folder() { return { ok: true, data: { path: s.pack.path } } },
        async handle_drop() { return { ok: true, data: {} } },
      } }
    }, state)
    await page.goto('http://127.0.0.1:8765/index.html', { waitUntil: 'networkidle' })
    await page.waitForTimeout(500)
    for (const [idx, name] of [[0, 'home'], [1, 'manage'], [2, 'settings'], [3, 'log']]) {
      if (idx) {
        await page.locator('.nav-item').nth(idx).click()
        await page.waitForTimeout(1200)
      }
      const violations = await page.evaluate(() => {
        const visible = (e) => {
          const r = e.getBoundingClientRect()
          return r.width > 0 && r.height > 0
        }
        const content = document.querySelector('.content')
        if (content && getComputedStyle(content).scrollbarWidth !== 'none') {
          out.push(['scrollbar-visible'])
        }
        const els = [...document.querySelectorAll('button, input')]
          .filter(visible)
          .map((e) => {
            const r = e.getBoundingClientRect()
            return { el: e, text: (e.innerText || e.value || e.getAttribute('aria-label') || '').trim().slice(0, 24), x: r.x, y: r.y, right: r.right, bottom: r.bottom }
          })
        const out = []
        for (let i = 0; i < els.length; i++) {
          const a = els[i]
          if (a.x < 1 || a.right > innerWidth - 1) out.push(['edge-x', a])
          // 卡片内的按钮/输入不能贴住卡片底线或右边线
          const card = els[i].el?.closest?.('.card')
          if (card) {
            const cr = card.getBoundingClientRect()
            if (cr.bottom - a.bottom < 12) out.push(['card-bottom-gap', a])
            if (cr.right - a.right < 12) out.push(['card-right-gap', a])
          }
          for (let j = i + 1; j < els.length; j++) {
            const b = els[j]
            const ox = Math.min(a.right, b.right) - Math.max(a.x, b.x)
            const oy = Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y)
            if (ox > 1.5 && oy > 1.5) out.push(['overlap', a, b])
          }
        }
        return out
      })
      if (violations.length) {
        failures.push({ advanced, w, h, page: name, violations })
      }
    }
    await page.close()
  }
}
await browser.close()
if (failures.length) {
  console.error(JSON.stringify(failures, null, 2))
  process.exit(1)
}
console.log('layout tests passed')
