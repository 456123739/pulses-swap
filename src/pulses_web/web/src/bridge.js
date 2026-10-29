/* pywebview bridge: the only place that talks to Python. */
export function whenReady() {
  // 不缓存 false：WebView2 冷启动/杀软扫描时注入可能晚于 1.8s，
  // 调用方可以稍后重试，而不是永久卡在错误态。
  if (window.pywebview?.api) return Promise.resolve(true)
  return new Promise((resolve) => {
    let settled = false
    const done = () => {
      if (settled) return
      settled = true
      resolve(Boolean(window.pywebview?.api))
    }
    window.addEventListener('pywebviewready', done, { once: true })
    setTimeout(done, 1800)
  })
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
