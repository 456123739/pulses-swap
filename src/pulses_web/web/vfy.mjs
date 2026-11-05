import { chromium } from 'playwright'
const FILE='file:///home/admin/111/_trailer/PulsesSwap-Trailer-v27.html?render=1'
const b=await chromium.launch({executablePath:'/home/admin/.cache/ms-playwright/chromium-1194/chrome-linux/chrome',args:['--no-sandbox']})
const pg=await b.newPage({viewport:{width:1280,height:720}})
const errs=[]; pg.on('pageerror',e=>errs.push(e.message.slice(0,120)))
await pg.goto(FILE,{waitUntil:'load'}); await pg.evaluate(()=>{const b=document.getElementById('gatePlay'); if(b) b.click();})
await pg.waitForTimeout(600)
console.log(await pg.evaluate(()=>({api:typeof window.__render, start:window.__tl?window.__tl.startTime():'no tl', bar:document.getElementById('bar').style.display})))
const check = (t)=>pg.evaluate((t)=>{
  for(let i=(window.__c||0); i<=Math.round(t*60); i++) window.__render(i/60);
  window.__c=Math.round(t*60); if(!window.__r0){window.__r0=1;}
  const caps=[...document.querySelectorAll('#txt > *')].filter(e=>parseFloat(getComputedStyle(e).opacity)>0.5).map(e=>e.textContent.trim().slice(0,20))
  const g=id=>{const e=document.querySelector(`[data-wid="${id}"]`);return e?e.textContent.trim().slice(0,22):'-'}
  return {t, caps, ver:g('info_version'), entry:g('version_entry'), btn:g('btn_apply')}
}, t)
for (const t of [1.2, 25.6]) console.log(JSON.stringify(await check(t)))
console.log('errors', errs.join('|')||'none')
await b.close()
