import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
const app = readFileSync(new URL('./src/App.jsx', import.meta.url), 'utf8')
const cloud = readFileSync(new URL('./src/components/CloudFiles.jsx', import.meta.url), 'utf8')
const handlerSource = app.split('const handleEvent = ')[1].split('\n    jobHandlerRef.current')[0]
function handler(overrides = {}) {
  const notices = []
  const context = { alive: true, submittingJobRef: {current: false}, pendingJobEvents: {current: []}, jobIdRef: {current: 'active'}, busyTimer: {current: null}, lastJobRef: {current: null}, autoRetryRef: {current: 0}, setSnap() {}, refresh() {}, clearBusy() {}, showToast: (...v) => notices.push(v), ...overrides }
  return { run: vm.runInNewContext(`(${handlerSource})`, context), context, notices }
}
test('terminal events arriving before invoke resolves are buffered', () => {
  const h = handler({submittingJobRef: {current: true}})
  h.run({type: 'job.done', jobId: 'active', data: {result: {}}})
  assert.equal(h.context.pendingJobEvents.current.length, 1)
  assert.equal(h.notices.length, 0)
})
test('old task terminal cannot complete current task', () => {
  const h = handler()
  h.run({type: 'job.done', jobId: 'old'})
  assert.equal(h.notices.length, 0)
})
for (const result of [{failed: [['a', 'offline']]}, {cancelled: true}, {ok: false}]) {
  test(`serialized task failure is visible: ${JSON.stringify(result)}`, () => {
    const h = handler()
    h.run({type: 'job.done', jobId: 'active', data: {result: {result}}})
    assert.equal(h.notices[0][1], 'warning')
  })
}
test('late cloud response cannot overwrite latest navigation', async () => {
  const pending = [], updates = []
  const context = { accountOk: true, accountKey: 'account', activeScope: {current: 'account'}, mounted: {current: true}, requestId: {current: 0}, targetPath: {current: '/'}, invoke: () => new Promise(resolve => pending.push(resolve)), setLoading() {}, setError() {}, setData: v => updates.push(v.path), setPath() {}, setTree() {}, setUpdatedAt() {}, Date }
  const source = cloud.split('const load = useCallback(')[1].split('\n  }, [accountOk, accountKey])')[0] + '\n  }'
  const load = vm.runInNewContext(`(${source})`, context)
  const a = load('/a'), b = load('/b')
  pending[1]({path: '/b'}); await b
  pending[0]({path: '/a'}); await a
  assert.deepEqual(updates, ['/b'])
  const c = load('/c'); context.mounted.current = false
  pending[2]({path: '/c'}); await c
  assert.deepEqual(updates, ['/b'])
})

function poller(status, eventHandler) {
  const source = app.split("const jobId = busy.jobId")[1].split("\n    const timer = setInterval(poll, 2000)")[0]
  const notices = []
  const ctx = {jobId: 'active', jobIdRef: {current: 'active'}, invoke: async () => status,
    jobHandlerRef: {current: eventHandler}, showToast: (...v) => notices.push(v)}
  return {run: vm.runInNewContext(`(async () => {${source}; await poll()})`, ctx), notices}
}
test('poll recovers done when completion event was dropped', async () => {
  let cleared = 0
  const h = handler({clearBusy: () => cleared++})
  const p = poller({status: 'done', result: {message: 'Recovered'}}, h.run)
  await p.run()
  assert.equal(cleared, 1)
  assert.equal(h.notices[0][0], 'Recovered')
  assert.equal(h.notices[0][1], 'success')
})
test('unknown status warns without unlocking task', async () => {
  let cleared = 0
  const p = poller({status: 'unknown'}, () => cleared++)
  await p.run()
  assert.equal(cleared, 0)
  assert.equal(p.notices[0][1], 'warning')
})
