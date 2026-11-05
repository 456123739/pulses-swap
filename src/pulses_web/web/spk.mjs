import { chromium } from 'playwright'
const b = await chromium.launch({ executablePath: '/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] })
const pg = await b.newPage({ viewport: { width: 1280, height: 900 } })
const errs = []
pg.on('pageerror', e => errs.push(e.message.slice(0, 140)))
pg.on('console', m => { if (m.type() === 'error') errs.push('C:' + m.text().slice(0, 140)) })
await pg.goto('file:///tmp/spike.html', { waitUntil: 'load' })
await pg.waitForTimeout(1600)
await pg.screenshot({ path: '/tmp/spike.png' })
const h = await pg.evaluate(() => document.getElementById('root').innerHTML.length)
console.log('root html len', h, '| errors:', errs.slice(0, 2).join(' | ') || 'none')
await b.close()
