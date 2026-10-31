/* pywebview bridge: the only place that talks to Python. */
function apiReady() {
  return typeof window.pywebview?.api?.invoke === 'function'
}

export function whenReady() {
  // pywebview 会先暴露 window.pywebview.api 对象，再异步挂载方法。
  // 只看对象存在会在冷启动时过早调用 api.invoke（WebView2 上就是
  // “invoke is not a function”并卡在错误态），必须等方法和 ready 事件。
  if (apiReady()) return Promise.resolve(true)
  return new Promise((resolve) => {
    let settled = false
    const done = () => {
      if (settled) return
      settled = true
      resolve(apiReady())
    }
    window.addEventListener('pywebviewready', done, { once: true })
    setTimeout(done, 1800)
  })
}

export function hasBridge() {
  return apiReady()
}

export async function invoke(method, params = {}) {
  const ready = await whenReady()
  if (!ready || !apiReady()) throw new Error('桌面桥接尚未就绪')
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
