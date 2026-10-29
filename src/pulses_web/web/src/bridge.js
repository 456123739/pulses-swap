/* pywebview bridge: the only place that talks to Python. */
let readyPromise

export function whenReady() {
  if (readyPromise) return readyPromise
  readyPromise = new Promise((resolve) => {
    const done = () => resolve(true)
    if (window.pywebview?.api) return done()
    window.addEventListener('pywebviewready', done, { once: true })
    // Browser-only development: let the UI render an explicit demo state.
    setTimeout(() => resolve(Boolean(window.pywebview?.api)), 1800)
  })
  return readyPromise
}

export function hasBridge() {
  return Boolean(window.pywebview?.api)
}

export async function invoke(method, params = {}) {
  if (!window.pywebview?.api) throw new Error('桌面桥接尚未就绪')
  const result = await window.pywebview.api.invoke(method, params)
  if (!result?.ok) {
    const error = new Error(result?.error?.message || '操作失败')
    error.code = result?.error?.code || 'ERROR'
    error.detail = result?.error?.detail || ''
    throw error
  }
  return result.data
}

export async function pickFolder() {
  if (!window.pywebview?.api) throw new Error('桌面桥接尚未就绪')
  const result = await window.pywebview.api.pick_folder()
  if (!result?.ok) throw new Error(result?.error?.message || '无法打开文件夹选择器')
  return result.data.path || ''
}

export function subscribe(handler) {
  const previous = window.PS
  window.PS = {
    ...(previous || {}),
    push(event) {
      try { handler(event) } catch (err) { console.error('event handler failed', err) }
    },
  }
  return () => {
    if (window.PS?.push) window.PS.push = () => {}
  }
}
