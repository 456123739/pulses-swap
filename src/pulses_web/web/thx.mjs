import { chromium } from 'playwright'
const b=await chromium.launch({executablePath:'/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']})
const pg=await b.newPage({viewport:{width:1280,height:720}})
await pg.goto('file:///home/admin/111/_trailer/PulsesSwap-Trailer-v27.html?render=1&v='+Date.now(),{waitUntil:'load'})
await pg.evaluate(()=>{const g=document.getElementById('gatePlay'); if(g) g.click()})
await pg.waitForTimeout(600)
console.log(await pg.evaluate(()=>{
  for(let i=0;i<=31.5*60;i++) window.__render(i/60)
  const out={}
  for(let i=1;i<=4;i++){
    const bar=document.querySelector(`[data-wid="th_${i}"]`); const lb=document.querySelector(`[data-wid="th_lbl_${i}"]`)
    const fill=bar&&bar.querySelector('.pg-fill')
    out['th'+i]={disp:bar?getComputedStyle(bar).display:'-', h:bar?bar.offsetHeight:0, fillW:fill?Math.round(fill.getBoundingClientRect().width):0, lbl:lb?lb.textContent.trim():'-'}
  }
  return JSON.stringify(out)
}))
await b.close()
