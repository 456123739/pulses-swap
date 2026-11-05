import { chromium } from 'playwright'
const b=await chromium.launch({executablePath:'/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']})
const pg=await b.newPage({viewport:{width:1920,height:1080}})
await pg.goto('file:///home/admin/111/_trailer/PulsesSwap-Trailer-v27.html?render=1&v='+Date.now(),{waitUntil:'load'})
await pg.evaluate(()=>{const g=document.getElementById('gatePlay'); if(g) g.click()})
await pg.waitForTimeout(700)
let cur=0
for (const t of process.argv.slice(2).map(Number)) {
  await pg.evaluate(({t,cur})=>{ for(let i=Math.round(cur*60); i<=Math.round(t*60); i++) window.__render(i/60) }, {t,cur})
  cur=t
  await pg.waitForTimeout(200)
  await pg.screenshot({ path:`/tmp/shots/q${t}.png` })
}
console.log('done')
await b.close()
