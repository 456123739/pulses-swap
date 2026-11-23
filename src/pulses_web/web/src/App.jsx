import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, Reorder, motion, useDragControls } from 'motion/react'
import Icon from './components/Icons.jsx'
import Hint from './components/Hint.jsx'
import CloudFiles from './components/CloudFiles.jsx'
import { hasBridge, invoke, pickFiles, pickFolder, subscribe, whenReady } from './bridge.js'

const EMPTY = {
  version: '', role: 'player',
  pack: { path: '', name: '', tacz: '', loaded: false },
  presets: [], selected: null, gunpacks: [], plan: null,
  online: { available: false, account: {}, binding: {} },
  settings: {}, recent: [], logs: [], capabilities: {},
}

// 苹果那种"有阻尼的弹簧"：数值越大越硬，damping 越大回弹越少。
const SPRING = { type: 'spring', stiffness: 430, damping: 34, mass: 0.7 }
const SPRING_SOFT = { type: 'spring', stiffness: 260, damping: 30, mass: 0.9 }
const SPRING_SNAP = { type: 'spring', stiffness: 620, damping: 38, mass: 0.6 }

// 预设没有配图，用名字哈希给每个预设一个稳定的强调色，列表才有层次。
// 用连续色相而不是固定几档，名字相近的预设也能分开；饱和度压住，避免花。
function presetAccent(name) {
  let hash = 0
  for (const ch of String(name || '')) hash = (hash * 131 + ch.codePointAt(0)) >>> 0
  return `hsl(${hash % 360} 34% 52%)`
}

const NAV = [
  { key: 'home', label: '主页', icon: 'home' },
  { key: 'manage', label: '管理', icon: 'manage' },
  { key: 'settings', label: '设置', icon: 'settings' },
  { key: 'log', label: '日志', icon: 'log' },
]

function Logo() {
  return (
    <div className="wordmark" aria-label="Pulses Swap">
      <span className="wordmark-bar" />
      <span className="wordmark-pulses">Pulses</span>
      <span className="wordmark-swap">Swap</span>
    </div>
  )
}

function Cover({ state }) {
  if (!state.active) return null
  return (
    <div className={`cover cover-${state.phase} ${state.target ? `cover-to-${state.target}` : ''}`} aria-hidden="true">
      <div className="cover-panel cover-left" />
      <div className="cover-panel cover-right" />
      <div className="cover-aura" />
      <div className="cover-brand">
        <span className="cover-kicker">{state.note || 'PULSES SWAP'}</span>
        <Logo />
        <div className="cover-credit">PULSES 0 Studio · NimShade &amp; DS</div>
      </div>
    </div>
  )
}

function Progress({ value, text }) {
  return (
    <div className="progress-wrap" role="progressbar" aria-valuemin="0" aria-valuemax="100"
      aria-valuenow={Math.round(value || 0)} aria-valuetext={text || undefined}>
      <div className="progress-track"><span style={{ transform: `scaleX(${Math.max(0.015, (value || 0) / 100)})` }} /></div>
      <span className="progress-label">{text}</span>
    </div>
  )
}

function Sidebar({ page, onNavigate, role, loggedIn, expanded, setExpanded, version, onSwitchRole, pack, presetCount }) {
  return (
    <aside className={`sidebar ${expanded ? 'expanded' : ''}`}
      onMouseEnter={() => setExpanded(true)} onMouseLeave={() => setExpanded(false)}>
      <div className="brand-row">
        <div className="brand-mark"><img src="./logo-sw.png" alt="" /></div>
        <div className="brand-copy">
          <strong>PULSES SWAP</strong>
          <span>v{version || '3.0.0'}</span>
        </div>
      </div>
      <nav className="nav" aria-label="主导航">
        {NAV.map((item) => (
          <button key={item.key} className={`nav-item ${page === item.key ? 'active' : ''}`}
            onClick={() => onNavigate(item.key)} title={item.label}>
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      {pack?.loaded && <button className="sidebar-pack" onClick={() => onNavigate('home')} title={pack.name}>
        <Icon name="folder" size={17} />
        <span className="sidebar-pack-copy"><strong>{pack.name}</strong><small>{presetCount} 个预设</small></span>
      </button>}
      <div className="sidebar-foot">
        <button className={`role-mini ${loggedIn ? role : 'offline'}`} onClick={onSwitchRole}
          title={loggedIn ? (role === 'developer' ? '开发者（点击切换）' : '玩家（点击切换）') : '未登录'}
          aria-label="切换身份">{loggedIn ? (role === 'developer' ? 'D' : 'P') : '—'}</button>
        <button className={`role-switch ${loggedIn ? '' : 'logged-out'}`} onClick={onSwitchRole}
          title={loggedIn ? (role === 'developer' ? '切换为玩家' : '切换为开发者') : '未登录 · 无法切换身份'}
          aria-label={loggedIn ? '切换身份' : '未登录 · 无法切换身份'}>
          <span className={`role-dot ${loggedIn ? role : 'offline'}`} />
          <span className="role-copy">
            {loggedIn ? (role === 'developer' ? '开发者' : '玩家') : '未登录'}
            <small>{loggedIn ? '切换身份' : '无法切换身份'}</small>
          </span>
        </button>
      </div>
    </aside>
  )
}

function Modal({ modal, onClose }) {
  const [value, setValue] = useState(modal?.value || '')
  const [password, setPassword] = useState('')
  const [presetName, setPresetName] = useState('')
  const [presetVersion, setPresetVersion] = useState('')
  const [cloudPath, setCloudPath] = useState('')
  const [uploadVersion, setUploadVersion] = useState('')
  const [uploadNotes, setUploadNotes] = useState('')
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const submitted = useRef(false)
  const cardRef = useRef(null)
  const previousFocus = useRef(null)
  useEffect(() => {
    setValue(modal?.value || ''); setPassword(''); submitted.current = false
    setError(''); setPending(false)
    if (!modal) return undefined
    previousFocus.current = document.activeElement
    const timer = setTimeout(() => cardRef.current?.focus(), 0)
    return () => { clearTimeout(timer); previousFocus.current?.focus?.() }
  }, [modal])
  useEffect(() => {
    if (modal?.kind === 'preset') {
      setPresetName(modal.preset?.name || '')
      setPresetVersion(modal.preset?.version || '')
    }
    if (modal?.kind === 'upload') {
      setCloudPath(modal.cloudPath || '')
      setUploadVersion(modal.version || '')
      setUploadNotes(modal.notes || '')
    }
  }, [modal?.kind, modal?.preset?.name, modal?.cloudPath])
  if (!modal) return null
  const submit = async () => {
    if (submitted.current || pending) return
    const callback = modal.onConfirm
    const payload = modal.kind === 'login'
      ? { username: value, password }
      : modal.kind === 'cloudadd' ? { url: value, password }
      : modal.kind === 'preset' ? { name: presetName.trim(), version: presetVersion.trim() }
      : modal.kind === 'upload' ? { cloud_path: cloudPath.trim(), version: uploadVersion.trim(), notes: uploadNotes.trim() }
      : value
    setError('')
    setPending(true)
    submitted.current = true
    try {
      await Promise.resolve(callback(payload))
      onClose()                       // 只有成功才关窗，失败保留已填内容
    } catch (err) {
      setError(err?.message || '操作失败，请再试一次')
      submitted.current = false
    } finally {
      setPending(false)
    }
  }
  return (
    <div className="modal-mask" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <motion.div ref={cardRef} tabIndex={-1} className="modal-card" role="dialog" aria-modal="true" aria-labelledby="modal-title"
        initial={{ opacity: 0, scale: 0.96, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ type: 'spring', stiffness: 380, damping: 30 }}
        onKeyDown={(e) => {
          if (e.key === 'Tab') {
            const focusables = [...e.currentTarget.querySelectorAll('button, input, [href]')].filter((n) => !n.disabled)
            if (!focusables.length) return
            const first = focusables[0], last = focusables[focusables.length - 1]
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
          } else if (e.key === 'Enter' && modal.kind === 'confirm' && e.target.tagName !== 'BUTTON') {
            e.preventDefault(); submit()
          }
        }}>
        <div className="modal-head"><h3 id="modal-title">{modal.title}</h3><button className="icon-btn" aria-label="关闭" onClick={onClose}><Icon name="close" /></button></div>
        {modal.body && <p className="modal-body">{modal.body}</p>}
        {modal.kind === 'prompt' && (
          <label className="field"><span>{modal.label || '名称'}</span>
            <input autoFocus value={value} onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') submit() }} /></label>
        )}
        {modal.kind === 'login' && (
          <>
            <label className="field"><span>蓝奏账号</span>
              <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder="手机号或邮箱" /></label>
            <label className="field"><span>密码</span>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') submit() }} /></label>
          </>
        )}
        {modal.kind === 'cloudadd' && (
          <>
            <label className="field"><span>分享链接</span>
              <input autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder="https://..." /></label>
            <label className="field"><span>提取密码</span>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') submit() }} /></label>
          </>
        )}
        {modal.kind === 'upload' && (
          <>
            <div className="preset-detail-meta">
              <span className="pill">{modal.preset?.count ?? 0} 个枪包</span>
              <span className="pill">首次上传会初始化云端</span>
            </div>
            <label className="field"><span>云端文件夹 <Hint text="默认 /PulsesSwap/预设名；可以改成你想要的路径，例如 /PulsesSwap/我的整合包。" /></span>
              <input autoFocus value={cloudPath} onChange={(e) => setCloudPath(e.target.value)}
                placeholder="/PulsesSwap/预设名" /></label>
            <div className="preset-detail-fields">
              <label className="field"><span>版本号</span>
                <input value={uploadVersion} onChange={(e) => setUploadVersion(e.target.value)} placeholder="v1.0.0" /></label>
              <label className="field"><span>更新说明（可选）</span>
                <input value={uploadNotes} onChange={(e) => setUploadNotes(e.target.value)} placeholder="例如：首次上传" /></label>
            </div>
            <p className="modal-hint">流程：生成本地清单 → 建云端目录 → 初始化 manifest → 上传枪包 → 提交 manifest → 取分享链接。进度会显示在右下角。</p>
          </>
        )}
        {modal.kind === 'preset' && (
          <>
            <div className="preset-detail-meta">
              <span className={`pill ${modal.preset?.applied ? 'success' : ''}`}>{modal.preset?.applied ? '已应用' : '未应用'}</span>
              <span>{modal.preset?.count ?? 0} 个枪包</span>
              {modal.details?.cloud?.url ? <span className="pill success">云端已绑定</span> : <span className="pill">未绑定云端</span>}
            </div>
            <div className="preset-detail-fields">
              <label className="field"><span>预设名称</span>
                <input autoFocus value={presetName} onChange={(e) => setPresetName(e.target.value)} /></label>
              <label className="field"><span>版本</span>
                <input value={presetVersion} onChange={(e) => setPresetVersion(e.target.value)} placeholder="v1.0.0" /></label>
            </div>
            {modal.details ? <>
              <div className="preset-cloud-info">
                <div><span>云端路径</span><strong>{modal.details.cloud?.cloud_path || '—'}</strong></div>
                <div><span>上次同步版本</span><strong>{modal.details.cloud?.last_version || '—'}</strong></div>
                <div><span>分享链接</span><strong className="path">{modal.details.cloud?.url || '未绑定'}</strong></div>
              </div>
              <div className="preset-gunpack-stats"><span>枪包</span><div>{modal.details.gunpacks?.length ? modal.details.gunpacks.map((g) => <span key={g}>{g}</span>) : <em>还没有枪包</em>}</div></div>
            </> : <p className="muted pad">正在读取云端与枪包信息…</p>}
            <p className="modal-hint">点击“保存修改”后生效；关闭窗口不会保存。</p>
          </>
        )}
        {error && <p className="modal-error" role="alert">{error}</p>}
        <div className="modal-actions">
          <button className="btn ghost" onClick={onClose}>取消</button>
          <button className="btn primary" disabled={pending} onClick={submit}>{pending ? '处理中…' : (modal.confirm || '确定')}</button>
        </div>
      </motion.div>
    </div>
  )
}

function JobBar({ busy, onCancel }) {
  const rate = useRef({ t: 0, cur: 0, value: 0 })
  useEffect(() => {
    if (!busy) { rate.current = { t: 0, cur: 0, value: 0 }; return }
    const now = performance.now()
    const cur = Number(busy.current) || 0
    const prev = rate.current
    if (!prev.t) rate.current = { t: now, cur, value: 0 }
    else if (cur > prev.cur) {
      const dt = (now - prev.t) / 1000
      if (dt >= 0.35) {
        const inst = (cur - prev.cur) / dt
        rate.current = { t: now, cur, value: prev.value ? prev.value * 0.55 + inst * 0.45 : inst }
      }
    }
  }, [busy?.current, busy?.updatedAt])
  if (!busy) return null
  const pct = Math.max(0, Math.min(100, Number(busy.progress) || 0))
  const speed = rate.current.value
  const speedText = speed > 0 ? `${(speed / 1048576).toFixed(1)} MB/s` : ''
  return (
    <div className="job-bar" role="status" aria-live="polite">
      <div className="job-bar-head"><strong>{busy.title || '处理中'}</strong><span>{Math.round(pct)}%</span></div>
      <div className={`job-bar-track ${busy.progress == null ? 'indeterminate' : ''}`}><i style={{ width: `${pct}%` }} /></div>
      <div className="job-bar-foot"><span className="job-bar-text">{busy.text || '准备中…'}</span>
        {speedText && <span className="job-bar-speed">{speedText}</span>}
        {busy.cancelable && onCancel && <button className="btn tiny ghost" onClick={onCancel}>取消</button>}
      </div>
    </div>
  )
}

function Toast({ toast, onAction }) {
  return (
    <AnimatePresence>
      {toast && (
        <motion.div key={toast.id} className={`toast ${toast.kind || 'info'}`} role="status" aria-live="polite"
          initial={{ opacity: 0, x: 30, scale: 0.97 }} animate={{ opacity: 1, x: 0, scale: 1 }}
          exit={{ opacity: 0, x: 20, scale: 0.98 }} transition={{ type: 'spring', stiffness: 420, damping: 32 }}>
          <span className="toast-dot" />{toast.message}
          {toast.action && <button className="toast-action" onClick={() => onAction(toast.action)}>{toast.action.label}</button>}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Empty({ title, hint, children }) {
  return <div className="empty"><div className="empty-orbit" /><h3>{title}</h3>{hint && <p>{hint}</p>}{children}</div>
}

// 差异状态 → 给人看的词。玩家和开发者看同一份差异，叫法不同。
const STATUS_LABELS = {
  player: { cloud_only: '缺失', changed: '变更', local_only: '多余', blocked: '无法处理', same: '一致' },
  developer: { cloud_only: '云端多余', changed: '有变更', local_only: '待上传', blocked: '无法处理', same: '一致' },
}
const STATUS_ORDER = ['cloud_only', 'changed', 'local_only', 'blocked']


// 根据当前状态给出"下一步该做什么"，用户不用自己判断。
function nextStepOf(snap) {
  if (!snap.pack.loaded) {
    return { tone: 'todo', title: '第 1 步：定位整合包', text: '把整合包文件夹拖进窗口，或点「选择整合包」。软件会自动找到里面的 tacz。', cta: '选择整合包', action: 'pick' }
  }
  if (!snap.presets.length) {
    return { tone: 'todo', title: '第 2 步：建一个预设', text: '预设就是一组枪包。点「新建」起个名字，或者从云端拉取别人做好的。', cta: '新建预设', action: 'create' }
  }
  const selected = snap.presets.find((p) => p.name === snap.selected)
  if (!selected) {
    return { tone: 'todo', title: '选一个预设', text: '从左边的预设列表点一个，就能看到它的枪包和操作。', cta: '', action: '' }
  }
  if (!(selected.count > 0)) {
    return { tone: 'warn', title: '这个预设还没有枪包', text: '先点「导入枪包」选 .zip 或文件夹；空预设不能替换，否则会把 tacz 清空。', cta: '导入枪包', action: 'import' }
  }
  const pending = (selected.pending || 0) + (selected.extra || 0)
  if (snap.role === 'developer') {
    if (!selected.bound) {
      return { tone: 'todo', title: '这个预设还没上传到云端', text: '点「上传到云端」会自动建 /PulsesSwap/预设名 并生成分享链接。', cta: '上传到云端', action: 'publishNew' }
    }
    if (pending > 0) {
      return { tone: 'todo', title: `有 ${pending} 项待上传`, text: '点「一键上传」，只传有变化的枪包，版本号自动 +1，云端多余文件保留。', cta: '一键上传', action: 'publishAuto' }
    }
    return { tone: 'done', title: '云端已是最新', text: '有改动时这里会提示；也可以随时重新上传。', cta: '', action: '' }
  }
  if (pending > 0) {
    return { tone: 'todo', title: `有 ${pending} 项可以处理`, text: '点「一键更新」，只下载有变化的枪包；已替换的预设会自动收回再换回去。', cta: '一键更新', action: 'sync' }
  }
  if (!selected.applied) {
    return { tone: 'ready', title: '可以替换到游戏里', text: '点「一键替换」，把这个预设的枪包写进整合包的 tacz；替换前会再确认一次。', cta: '一键替换', action: 'apply' }
  }
  if (!snap.online.binding?.url) {
    return { tone: 'done', title: '已经在游戏里用了', text: '想以后一键更新，再把开发者给你的分享链接绑上（可选）；不绑定也能正常替换。', cta: '', action: '' }
  }
  return { tone: 'done', title: '已经是最新', text: '需要换一组枪包时，随时可以重新替换。', cta: '', action: '' }
}

function NextStep({ step, onAct }) {
  if (!step) return null
  return (
    <section className={`next-step tone-${step.tone}`} aria-label="下一步">
      <span className="next-dot" aria-hidden="true" />
      <div className="next-copy"><strong>{step.title}</strong><span>{step.text}</span></div>
      {step.cta && <button className="btn small" onClick={() => onAct(step.action)}>{step.cta}</button>}
    </section>
  )
}

function statusLabel(status, role) {
  return (STATUS_LABELS[role] || STATUS_LABELS.player)[status] || ''
}

function GunpackLegend({ summary, role, bound }) {
  const counts = summary || {}
  const shown = STATUS_ORDER.filter((k) => counts[k] > 0)
  if (!shown.length) {
    return bound
      ? <div className="gunpack-legend"><span className="muted">还没检查差异：点下方「检查差异」，这里会按云端标色</span></div>
      : null
  }
  return (
    <div className="gunpack-legend">
      {shown.map((k) => (
        <span className="legend-chip" data-kind={k} key={k}>
          <i className="gp-dot" />{statusLabel(k, role)} {counts[k]}
        </span>
      ))}
      {counts.same > 0 && <span className="legend-chip" data-kind="same"><i className="gp-dot" />一致 {counts.same}</span>}
    </div>
  )
}

function PresetRow({ item, selected, role, onSelect, onRename, onDelete, onDetails, onUpdate }) {
  const pending = (item.pending || 0) + (item.extra || 0)
  const updateWord = role === 'developer' ? '上传' : '更新'
  const accent = presetAccent(item.name)
  const [menuOpen, setMenuOpen] = useState(false)
  return (
    <motion.div
      layout
      className={`preset-row ${selected ? 'selected' : ''}`}
      style={{ '--preset-accent': accent }}
      tabIndex={0}
      onClick={() => onSelect(item.name)}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(item.name) } }}
      onContextMenu={(e) => { e.preventDefault(); onDetails(item) }}
      whileHover={{ scale: 1.015, y: -1 }}
      whileTap={{ scale: 0.985 }}
      transition={SPRING}
    >
      <span className="preset-bar" aria-hidden="true" />
      <span className="preset-sheen" aria-hidden="true" />
      <div className="preset-main">
        <strong>{item.name}</strong>
        <span title={item.check_summary || ''}>
          {item.version || 'v1.0.0'} · {item.count || 0} 个枪包
          {item.needs_update && item.check_summary ? ` · ${item.check_summary}` : ''}
        </span>
      </div>
      {item.applied && <span className="pill success">已应用</span>}
      {item.bound && (
        <button className="mini-btn" data-testid={`preset-update-${item.name}`}
          data-quiet={!item.needs_update || undefined}
          title={item.check_summary || (item.checked_at ? '已是最新' : '还没检查过，点一下会检查并更新')}
          onClick={(e) => { e.stopPropagation(); onUpdate(item) }}>
          <Icon name="refresh" size={12} />{updateWord}{pending > 0 ? ` ${pending}` : ''}
          <Hint text={role === 'developer'
            ? '把这个预设的改动上传到云端，云端多余文件保留。'
            : '把这个预设更新到云端最新，再自动换回游戏。'} />
        </button>
      )}
      <div className="row-menu-wrap" onClick={(e) => e.stopPropagation()}>
        <button className="row-menu-btn" aria-haspopup="menu" aria-expanded={menuOpen}
          aria-label="更多操作" onClick={() => setMenuOpen((v) => !v)}>⋯</button>
        {menuOpen && (
          <div className="row-menu" role="menu">
            <button role="menuitem" onClick={() => { setMenuOpen(false); onDetails(item) }}>详情</button>
            <button role="menuitem" onClick={() => { setMenuOpen(false); onRename(item) }}>重命名</button>
            <button role="menuitem" className="danger" onClick={() => { setMenuOpen(false); onDelete(item) }}>删除</button>
          </div>
        )}
      </div>
    </motion.div>
  )
}

function PresetItemRow({ item, selected, role, onSelect, onRename, onDelete, onDetails, onUpdate }) {
  const controls = useDragControls()
  return (
    <Reorder.Item value={item.name} as="div" className="preset-item"
      dragListener={false} dragControls={controls}
      whileDrag={{ scale: 1.02, boxShadow: '0 14px 30px rgba(44, 62, 63, .14)' }}
      transition={SPRING}>
      <button className="preset-grip" aria-label="拖动排序" title="按住拖动排序"
        onPointerDown={(e) => { e.preventDefault(); controls.start(e) }}>⠿</button>
      <PresetRow item={item} selected={selected} role={role}
        onSelect={onSelect} onRename={onRename} onDelete={onDelete}
        onDetails={onDetails} onUpdate={onUpdate} />
    </Reorder.Item>
  )
}

function Home({ snap, actions, busy, publishNotes = '' }) {
  const selected = snap.presets.find((p) => p.name === snap.selected)
  const animations = snap.settings?.animations !== false
  const [celebrate, setCelebrate] = useState(false)
  const wasApplied = useRef(Boolean(selected?.applied))
  const lastName = useRef(selected?.name)
  const [recentOpen, setRecentOpen] = useState(false)
  const recentWrapRef = useRef(null)
  useEffect(() => {
    if (!recentOpen) return undefined
    const onDown = (e) => {
      if (!recentWrapRef.current?.contains(e.target)) setRecentOpen(false)
    }
    const onKey = (e) => { if (e.key === 'Escape') setRecentOpen(false) }
    document.addEventListener('pointerdown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [recentOpen])
  useEffect(() => {
    const now = Boolean(selected?.applied)
    if (lastName.current !== selected?.name) {
      lastName.current = selected?.name
      wasApplied.current = now
      return undefined
    }
    if (!wasApplied.current && now) {
      setCelebrate(true)
      const timer = setTimeout(() => setCelebrate(false), 1500)
      wasApplied.current = now
      return () => clearTimeout(timer)
    }
    wasApplied.current = now
  }, [selected?.applied, selected?.name])
  const openPack = async () => {
    setRecentOpen(false)
    try {
      const path = await pickFolder()
      if (path) actions.openPack(path)
    } catch (err) { actions.toast(err.message, 'error') }
  }
  const toggleRecent = () => {
    if (!snap.recent?.length) { openPack(); return }
    setRecentOpen((open) => !open)
  }
  const nextStep = nextStepOf(snap)
  const runNext = (action) => {
    if (action === 'pick') openPack()
    else if (action === 'create') actions.prompt('新建预设', '名称', '', (v) => actions.createPreset(v))
    else if (action === 'cloud') actions.addFromCloud()
    else if (action === 'sync' && selected) (snap.role === 'developer' ? actions.publishAuto : actions.syncAuto)(selected.name)
    else if (action === 'apply' && selected) actions.apply(selected)
    else if (action === 'import' && selected) actions.importGunpacks(selected.name)
    else if (action === 'publishNew' && selected) actions.openUpload(selected.name)
    else if (action === 'publishAuto' && selected) actions.publishAuto(selected.name)
  }
  return (
    <div className="page home-page">
      <div className="page-head home-head">
        <div><span className="eyebrow">WORKSPACE</span><h1>枪包预设</h1></div>
        {snap.pack.loaded
          ? <div className="pack-inline" title={snap.pack.path}>
              <span className="status-dot ready" />
              <div><strong>{snap.pack.name}</strong><span>{snap.pack.path}</span></div>
              <button className="text-btn" onClick={openPack}>切换</button>
            </div>
          : <span className="pill">未加载整合包</span>}
      </div>
      <NextStep step={nextStep} onAct={runNext} />

      {!snap.pack.loaded ? (
        <>
          <motion.section className="home-hero empty-hero" aria-label="导入整合包"
            onClick={(e) => { if (!e.target.closest('button, .recent-popover')) openPack() }}
            initial={animations ? { opacity: 0, y: 8 } : false} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: animations ? 0.34 : 0, ease: [0.22, 1, 0.36, 1] }}>
            <div className="hero-copy">
              <span className="eyebrow">WORKSPACE READY</span>
              <div className="hero-title"><h2>把整合包拖进窗口</h2><span className="pill">自动定位 tacz</span></div>
              <p>拖入整合包文件夹后会直接创建默认预设并进入工作区；也可以手动选择目录。</p>
              <div className="hero-facts">
                <span><b>0</b> 个预设</span>
                <span><b>待导入</b> 整合包</span>
                <span><b>拖入</b> 或选择</span>
              </div>
            </div>
            <div className="hero-actions" onClick={(e) => e.stopPropagation()}>
              <div className="recent-switch" ref={recentWrapRef}>
                <button className={`btn hero-primary ${recentOpen ? 'recent-open' : ''}`}
                  onClick={toggleRecent} aria-haspopup="listbox" aria-expanded={recentOpen}>
                  <Icon name="folder" size={21} />选择整合包
                  {(snap.recent || []).length > 0 && <Icon name="chevron" size={15} className="recent-chevron" />}
                </button>
                {recentOpen && <div className="recent-popover" role="listbox" aria-label="最近打开">
                  <div className="recent-popover-head"><span className="eyebrow">RECENT</span><span>最近打开</span></div>
                  <div className="recent-popover-scroll">
                    {(snap.recent || []).map((r) => (
                      <button key={r.path} className="recent-open-row" role="option" onClick={() => actions.openPack(r.path)} title={r.path}>
                        <span className="recent-open-icon"><Icon name="folder" size={16} /></span>
                        <span className="recent-open-copy"><strong>{r.name || r.path}</strong><small>{r.path}</small></span>
                        <Icon name="chevron" size={14} />
                      </button>
                    ))}
                  </div>
                  <button className="recent-open-row browse-row" onClick={() => { setRecentOpen(false); openPack() }}>
                    <span className="recent-open-icon"><Icon name="plus" size={15} /></span>
                    <span className="recent-open-copy"><strong>浏览其他文件夹…</strong><small>选一个整合包根目录</small></span>
                  </button>
                </div>}
              </div>
              <button className="drop-caption" onClick={() => openPack()}>点击选择，或拖入任意文件/文件夹</button>
            </div>
          </motion.section>
          <div className="home-grid empty-home-grid">
            <section className="card presets-card">
              <div className="card-head"><div><span className="eyebrow">PRESETS</span><h2>预设 <span className="count-badge">0</span></h2></div>
                <button className="btn small" disabled><Icon name="plus" />新建</button></div>
              <div className="empty-list"><Icon name="folder" size={22} /><strong>导入后自动生成</strong><span>整合包里的 tacz 会被识别为第一个预设。</span></div>
            </section>
            <section className="card detail-card recent-card">
              <div className="card-head"><div><span className="eyebrow">RECENT</span><h2>最近打开</h2></div>
                <span className="pill">{(snap.recent || []).length}</span></div>
              {(snap.recent || []).length > 0 ? <>
                <p className="recent-hint">拖入整合包内的任意文件/文件夹也能识别；也可以直接选择最近记录。</p>
                <div className="recent-open-scroll">
                  {snap.recent.map((r) => (
                    <button key={r.path} className="recent-open-row" onClick={() => actions.openPack(r.path)} title={r.path}>
                      <span className="recent-open-icon"><Icon name="folder" size={16} /></span>
                      <span className="recent-open-copy"><strong>{r.name || r.path}</strong><small>{r.path}</small></span>
                      <Icon name="chevron" size={14} />
                    </button>
                  ))}
                </div>
              </> : <div className="empty-list"><Icon name="download" size={22} /><strong>拖入即可开始</strong><span>拖入整合包内的任意文件/文件夹都能定位到 tacz；预设和枪包列表会显示在这里。</span></div>}
            </section>
          </div>
        </>
      ) : (
        <>
          <motion.section className="home-hero" aria-label="主要操作"
            initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: animations ? 0.34 : 0, ease: [0.22, 1, 0.36, 1] }}>
            <motion.div className="hero-copy" key={selected?.name || 'none'}
              initial={animations ? { opacity: 0, y: 5 } : false} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: animations ? 0.28 : 0, ease: [0.22, 1, 0.36, 1] }}>
              <span className="eyebrow">SELECTED PRESET</span>
              <div className="hero-title">
                <h2>{selected ? selected.name : '选择一个预设'}</h2>
                {selected && <span className={`pill ${selected.applied ? 'success' : ''}`}>{selected.applied ? '已应用' : '待替换'}</span>}
              </div>
              <p>{selected
                ? (selected.applied ? '这个预设已经写入整合包。需要恢复枪包时，可以重新替换。' : '把预设里的枪包写入当前整合包，替换前会再确认一次。')
                : '从左侧预设列表选一个，再执行替换。'}</p>
              <div className="hero-facts">
                <span><b>{selected?.version || '—'}</b> 版本</span>
                <span><b>{selected?.count ?? 0}</b> 个枪包</span>
                <span><b>{snap.online.binding?.url ? '已绑定' : '未绑定'}</b> 云端</span>
                <span><b>{snap.settings?.online_sync_clean ? '完全同步' : '保留多余'}</b> 本地多余</span>
              </div>
            </motion.div>
            <div className="hero-actions">
              {selected?.applied
                ? <button className={`btn hero-primary applied-state ${celebrate ? 'is-applied' : ''}`}
                    aria-label="当前预设已应用，点击重新替换" disabled={busy}
                    onClick={() => actions.apply(selected)} title="重新把这个预设写进整合包">
                    <Icon name="check" size={21} />已应用 · 重新替换
                  </button>
                : <button className="btn hero-primary" disabled={!selected || busy || (selected?.count ?? 0) === 0}
                    title={(selected?.count ?? 0) === 0 ? '先导入枪包，再替换' : undefined}
                    onClick={() => selected && actions.apply(selected)}>
                    <Icon name="check" size={21} />一键替换
                    <Hint text="把这个预设里的枪包写进整合包的 tacz。替换前会再确认一次，不会动别的文件。" />
                  </button>}
              {snap.role === 'player' ? <>
                <button className="btn hero-secondary cloud-action" disabled={busy || snap.online.available === false}
                  onClick={actions.addFromCloud}><Icon name="cloud" size={17} />从云端拉取预设
                  <Hint text="粘贴别人给的分享链接和提取码，软件会自动下载这个预设并绑定。" />
                </button>
                {selected && snap.online.binding?.url && (
                  <button className="btn hero-secondary" disabled={busy}
                    data-testid="one-click-update"
                    onClick={() => actions.syncAuto(selected.name)}>
                    <Icon name="refresh" size={17} />一键更新
                    {(selected.pending + selected.extra) > 0 && <span className="btn-count">{selected.pending + selected.extra}</span>}
                    <Hint text={snap.settings?.online_sync_clean
                      ? '只下载云端有变化的枪包；本地多出来的会删到回收站（设置里可关）。已替换的预设会先收回、更新完再换回去。'
                      : '只下载云端有变化的枪包；本地多出来的保留不动。已替换的预设会先收回、更新完再换回去。'} />
                  </button>
                )}
                {(snap.online.bound_count || 0) > 0 && <button className="btn hero-secondary" disabled={busy}
                  onClick={actions.syncAllAuto}><Icon name="refresh" size={17} />一键更新全部
                  <Hint text="把所有绑定过云端的预设都检查一遍，有更新就下载，已替换的会自动换回去。" />
                </button>}
              </> : selected && !snap.online.binding?.url
                ? <button className="btn hero-secondary cloud-action" disabled={busy}
                    onClick={() => actions.openUpload(selected.name)}><Icon name="upload" size={17} />上传到云端
                    <Hint text="在云端给这个预设建一个文件夹并上传全部枪包，完成后会给你一条分享链接。" />
                  </button>
                : <>
                  {selected && snap.online.binding?.url && (
                    <button className="btn hero-secondary" disabled={busy}
                      data-testid="one-click-upload"
                      onClick={() => actions.publishAuto(selected.name)}>
                      <Icon name="upload" size={17} />一键上传
                      {(selected.pending + selected.extra) > 0 && <span className="btn-count">{selected.pending + selected.extra}</span>}
                      <Hint text="只上传有变化的枪包，版本号自动 +1；云端多出来的文件不动。" />
                    </button>
                  )}
                  {(snap.online.bound_count || 0) > 0 && <button className="btn hero-secondary" disabled={busy}
                    onClick={() => actions.publishAllAuto(publishNotes)}><Icon name="upload" size={17} />一键上传全部
                    <Hint text="把所有绑定过云端的预设扫一遍，有变化就递增版本并上传。" />
                  </button>}
                  {!selected && <button className="btn hero-secondary" disabled>
                    <Icon name="chevron" size={17} />先在左侧选一个预设
                  </button>}
                </>}
            </div>
            {snap.plan?.offline && <p className="auto-note warning-note">云端暂时连不上，下面用的是上次缓存的结果；网络恢复后再点一次会自动走网络。</p>}
            {busy && <div className="hero-progress"><Progress value={busy.progress} text={busy.text || busy.title} /></div>}
          </motion.section>

          <div className="home-grid">
            <section className="card presets-card">
              <div className="card-head">
                <div><span className="eyebrow">PRESETS</span><h2>预设 <span className="count-badge">{snap.presets.length}</span></h2></div>
                <div className="button-row"><button className="btn small ghost" onClick={() => actions.select(snap.selected)} disabled={!snap.selected}><Icon name="refresh" />刷新</button>
                  <button className="btn small" onClick={() => actions.prompt('新建预设', '名称', '', (v) => actions.createPreset(v))}><Icon name="plus" />新建</button></div>
              </div>
              <Reorder.Group axis="y" values={snap.presets.map((p) => p.name)}
                onReorder={(order) => actions.reorderPresets(order)} className="preset-list" as="div">
                {snap.presets.length === 0 ? <p className="muted pad">还没有预设</p> : snap.presets.map((p) => (
                  <PresetItemRow key={p.name} item={p} selected={p.name === snap.selected} role={snap.role}
                    onSelect={actions.select} onRename={actions.rename} onDelete={actions.delete}
                    onDetails={actions.presetDetails}
                    onUpdate={(item) => (snap.role === 'developer' ? actions.publishAuto(item.name) : actions.syncAuto(item.name))} />
                ))}
              </Reorder.Group>
            </section>

            <motion.section className="card detail-card" key={selected?.name || 'none'}
              initial={animations ? { opacity: 0, y: 7 } : false} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: animations ? 0.28 : 0, ease: [0.22, 1, 0.36, 1] }}>
              <div className="card-head"><div><span className="eyebrow">DETAIL</span><h2>{selected?.name || '未选择'}</h2></div>
                {selected && <span className={`pill ${selected.applied ? 'success' : ''}`}>{selected.applied ? '已应用' : '未应用'}</span>}</div>
              {selected ? <>
                <div className="detail-row"><span>版本</span><strong>{selected.version}</strong>
                  <button className="text-btn" onClick={() => actions.prompt('修改版本号', '版本号', selected.version, (v) => actions.saveVersion(selected.name, v))}>修改</button></div>
                <div className="detail-row"><span>枪包</span>
                  <button className="text-btn" data-testid="import-gunpacks" disabled={selected.applied || busy}
                    title={selected.applied ? '已应用到游戏，先点「收回」再导入' : '从电脑里选 .zip 或枪包文件夹'}
                    onClick={() => actions.importGunpacks(selected.name)}>导入枪包
                    <Hint text={selected.applied
                      ? '这个预设已经写进游戏了。先点下面的「收回」，再导入新枪包。'
                      : '选 .zip 或文件夹，软件会把它们复制进这个预设；同名的会跳过，不动游戏里的文件。'} /></button>
                  {selected.applied && <button className="text-btn danger-text" data-testid="detach-preset"
                    disabled={busy} onClick={() => actions.detach(selected.name)}>收回
                    <Hint text="把枪包从 tacz 拿回预设目录，游戏里会变回没有枪包的状态；文件不会丢。" /></button>}</div>
                <div className="detail-row"><span>云端</span><strong>{snap.online.binding?.url ? '已绑定' : '未绑定'}</strong></div>
                <div className="gunpack-head"><span>枪包列表</span><span className="muted">共 {snap.gunpacks.length} 个</span></div>
                <GunpackLegend summary={snap.gunpack_summary} role={snap.role} bound={Boolean(snap.online.binding?.url)} />
                <div className="gunpack-list">
                  {snap.gunpacks.length === 0 ? <div className="gunpack-empty">
                    <strong>这个预设还没有枪包</strong>
                    <span>点上面「导入枪包」选 .zip 或文件夹，或者从云端拉取别人做好的。</span>
                    <button className="btn small" onClick={() => actions.importGunpacks(selected.name)}>导入枪包</button>
                  </div> : (
                    <AnimatePresence mode="popLayout" initial={false}>
                      {snap.gunpacks.map((g, i) => (
                        <motion.div className={`gunpack-row status-${g.status || 'unknown'}`} key={`${snap.selected}:${g.name}`}
                          initial={animations ? { opacity: 0, y: 10, scale: 0.985 } : false}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={animations ? { opacity: 0, y: -4 } : { opacity: 1 }}
                          transition={animations
                            ? { opacity: { duration: 0.28, delay: i * 0.035 }, y: { ...SPRING_SOFT, delay: i * 0.035 }, scale: SPRING_SOFT }
                            : { duration: 0 }}
                          whileHover={animations ? { scale: 1.022, y: -1.5 } : undefined}
                          whileTap={animations ? { scale: 0.988 } : undefined}
                          onMouseMove={(e) => {
                            if (!animations) return
                            const box = e.currentTarget.getBoundingClientRect()
                            e.currentTarget.style.setProperty('--mx', `${((e.clientX - box.left) / box.width) * 100}%`)
                            e.currentTarget.style.setProperty('--my', `${((e.clientY - box.top) / box.height) * 100}%`)
                          }}
                          title={g.status ? `${statusLabel(g.status, snap.role)}：${g.name}` : g.name}>
                          <span className="gp-glow" aria-hidden="true" />
                          <i className="gp-dot" />
                          <Icon name="folder" size={15} />
                          <span className="gp-name">{g.name}</span>
                          <span className="muted">{g.type || 'zip'}</span>
                          {g.status
                            ? <span className="gp-badge" data-kind={g.status}>{statusLabel(g.status, snap.role)}</span>
                            : <span className="gp-badge" data-kind="unknown">未检查</span>}
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  )}
                </div>
                <div className="detail-footer">
                  <span className="muted">{snap.online.binding?.url ? '云端已绑定，可增量同步' : '尚未绑定云端来源'}</span>
                  <div className="button-row">
                    {snap.online.binding?.url && <button className="btn ghost small" data-testid="check-diff"
                      disabled={busy} onClick={() => actions.check(selected.name)}><Icon name="refresh" />检查差异
                      <Hint text="只做对比，不改任何文件：看清楚云端和本地差在哪，再决定要不要更新。" />
                    </button>}
                    <button className="btn ghost small" onClick={actions.openTacz}><Icon name="folder" />打开 TACZ</button>
                    <button className="btn ghost small" onClick={actions.openCloud}>云端文件</button></div>
                </div>
              </> : <div className="detail-empty"><p>从左侧选择一个预设</p><span>选中后可在这里查看版本、云端绑定和枪包列表。</span></div>}
            </motion.section>
          </div>
        </>
      )}
    </div>
  )
}

function Manage({ snap, actions, busy, tab = 'overview', onTab, publishNotes = '', setPublishNotes = () => {} }) {
  const animations = snap.settings?.animations !== false
  const advanced = snap.settings?.advanced_actions === true
  const [url, setUrl] = useState(snap.online.binding?.url || '')
  const [password, setPassword] = useState(snap.online.binding?.password || '')
  const [showPwd, setShowPwd] = useState(false)
  const onlineReady = snap.online.available !== false
  const [selection, setSelection] = useState(null)
  const [publishVersion, setPublishVersion] = useState('')
  const selected = snap.presets.find((p) => p.name === snap.selected)
  useEffect(() => { setUrl(snap.online.binding?.url || ''); setPassword(snap.online.binding?.password || '') }, [snap.online.binding?.url, snap.online.binding?.password])
  useEffect(() => { setPublishVersion(selected?.version || '') }, [selected?.name, selected?.version])
  const planMismatch = Boolean(snap.plan && snap.plan.role !== snap.role)
  const plan = planMismatch ? null : snap.plan
  const selectedPaths = selection ?? new Set((plan?.items || []).filter((i) => i.checked).map((i) => i.path))
  const toggle = (path) => {
    const next = new Set(selectedPaths)
    next.has(path) ? next.delete(path) : next.add(path)
    setSelection(next)
  }
  const isDeveloper = snap.role === 'developer'
  const boundCount = snap.online.bound_count || 0
  const selectedBound = Boolean(snap.online.binding?.url)
  const autoLabel = isDeveloper ? '一键上传全部' : '一键更新全部'
  const autoHint = isDeveloper
    ? '自动遍历所有已绑定预设，扫描、递增版本并上传变更；不会删除云端多余文件。'
    : '自动遍历所有已绑定预设，下载更新并清理本地多余项；已应用的预设会自动替换。'
  const runAuto = () => isDeveloper ? actions.publishAllAuto() : actions.syncAllAuto()
  return (
    <div className="page manage-page">
      <div className="page-head"><div><span className="eyebrow">GLOBAL</span><h1>管理</h1></div>
        <div className="head-actions">
          <button className="btn ghost" onClick={actions.login}>{snap.online.account?.label ? '账号' : '登录蓝奏'}</button>
          <button className="btn ghost" onClick={() => actions.switchRole(isDeveloper ? 'player' : 'developer')}>
            {isDeveloper ? '切换为玩家' : '切换为开发者'}
          </button>
        </div></div>
      <div className="tabs manage-tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'overview'} className={tab === 'overview' ? 'active' : ''} onClick={() => onTab?.('overview')}>总览</button>
        <button role="tab" aria-selected={tab === 'cloud'} className={tab === 'cloud' ? 'active' : ''} onClick={() => onTab?.('cloud')}>云端文件</button>
      </div>
      {tab === 'cloud' ? <CloudFiles snap={snap} actions={actions} busy={busy} /> : <>
      <section className="action-deck manage-action" aria-label="管理主要操作">
        <div className="action-copy">
          <span className="eyebrow">ONE CLICK</span>
          <h2>全部云端预设 · {boundCount} 个</h2>
          <p>{boundCount ? autoHint : (isDeveloper
            ? '还没有云端预设：先在左侧选一个预设，点「上传到云端」。'
            : '还没有绑定云端来源：从云端拉取预设，或先选一个本地预设直接替换。')}</p>
          <div className="action-meta">
            <span>{boundCount} 个已绑定</span>
            <span>{plan?.summary || (isDeveloper ? '待上传检查' : '待更新检查')}</span>
            <span>{isDeveloper ? '开发者' : '玩家'}</span>
          </div>
          {isDeveloper && <label className="field publish-notes-inline">
            <span>这次更新了什么（可选） <Hint text="玩家更新时会看到这句话；留空会自动写「一键发布 · 上传 N 项」。" /></span>
            <input value={publishNotes} onChange={(e) => setPublishNotes(e.target.value)}
              placeholder="例如：新增 3 把枪，修了音效" />
          </label>}
        </div>
        <div className="action-buttons">
          <button className="btn xl primary action-primary" disabled={!boundCount || busy}
            onClick={() => (isDeveloper ? actions.publishAllAuto(publishNotes) : runAuto())}>
            <Icon name={isDeveloper ? 'upload' : 'cloud'} size={20} />{autoLabel}
            <Hint text={isDeveloper
              ? '遍历所有绑定过云端的预设：有变化就递增版本号上传，云端多余文件不会删。'
              : '遍历所有绑定过云端的预设：有更新就下载，删除项进回收站，已替换的自动换回去。'} />
          </button>
          {isDeveloper && selected && !selectedBound && <button className="btn action-secondary create-cloud-action"
            disabled={busy} onClick={() => actions.openUpload(selected.name)}>
            <Icon name="upload" size={17} />上传到云端</button>}
          {advanced && <button className="btn action-secondary" disabled={!selected || !url || busy}
            onClick={() => actions.check(selected.name)}><Icon name="refresh" size={17} />检查差异</button>}
          {advanced && isDeveloper && <button className="btn action-secondary" disabled={!selected || busy}
            onClick={() => actions.publishPlan(selected.name)}><Icon name="upload" size={17} />仅生成计划</button>}
        </div>
      </section>
      <div className="stat-grid">
        <div className="stat"><span>预设计数</span><strong>{snap.presets.length}</strong><small>当前整合包</small></div>
        <div className="stat"><span>云端状态</span><strong>{snap.online.binding?.url ? '已绑定' : '未绑定'}</strong><small>{plan?.summary || '尚未检查'}</small></div>
        <div className="stat"><span>账号</span><strong>{snap.online.account?.label ? '已认证' : '未登录'}</strong><small>{snap.online.account?.label || '本地模式'}</small></div>
        <div className="stat"><span>发布历史</span><strong>{(snap.online.binding?.history || []).length}</strong><small>最近记录</small></div>
      </div>
      <section className={`card plan-card ${!plan ? 'plan-empty' : ''}`}>
        <div className="card-head"><div><span className="eyebrow">DIFF</span><h2>{isDeveloper ? '待上传差异' : '云端差异'}</h2></div>
          {plan && <span className="pill">{plan.summary}</span>}</div>
        {plan?.offline && <p className="auto-note warning-note">云端暂时连不上，这是上次缓存的结果；恢复后再点「{autoLabel}」会重新联网检查。</p>}
        {planMismatch ? <p className="auto-note warning-note">当前差异计划属于另一个身份，已隐藏；点上方“{autoLabel}”会按当前身份重新计算。</p>
          : !plan ? <p className="muted pad">不需要手动检查。点上方“{autoLabel}”，软件会逐个比对所有已绑定预设并完成操作。</p> : <>
          {advanced && isDeveloper && <div className="publish-row">
            <label className="field">
              <span>发布版本号 <Hint text="给玩家看的版本，建议只改最后一位，例如 v1.0.4 → v1.0.5。" /></span>
              <input value={publishVersion} onChange={(e) => setPublishVersion(e.target.value)} placeholder={selected?.version || 'v1.0.0'} spellCheck={false} />
            </label>
            <label className="field">
              <span>发布说明 <Hint text="玩家更新时会看到这段文字，写清这次改了什么就行。" /></span>
              <input value={publishNotes} onChange={(e) => setPublishNotes(e.target.value)} placeholder="例如：新增 3 把枪，修了音效" />
            </label>
          </div>}
          {!advanced && isDeveloper && <p className="auto-note">版本号会自动在当前版本上 +1，说明写「一键发布 · 上传 N 项」。想自己写？<button className="text-btn" onClick={() => actions.updateSettings({ advanced_actions: true })}>打开高级操作</button></p>}
          {advanced ? <div className="plan-cta">
            {!isDeveloper
              ? <button className="btn primary plan-primary" disabled={!selected || !selectedPaths.size || busy} onClick={() => actions.sync(selected.name, [...selectedPaths])}>同步选中</button>
              : snap.publish_ready
              ? <button className="btn primary plan-primary" disabled={busy} onClick={() => actions.publish(selected.name, publishVersion || selected.version, publishNotes, [...selectedPaths])}>发布选中</button>
              : <button className="btn primary plan-primary" disabled={busy || !selected} onClick={() => actions.publishPlan(selected.name)}>生成发布计划</button>}
          </div> : <p className="auto-note">软件已按最稳妥方案选择：{isDeveloper ? '只上传变更，保留云端多余文件' : '下载更新，并按设置处理本地多余项'}。</p>}
          <div className="plan-list">
            <AnimatePresence mode="popLayout" initial={false}>
              {plan.items.map((item, i) => (
                <motion.div key={`${snap.selected}:${snap.plan?.generation || 0}:${item.path}`}
                  className={`diff-row ${item.action}`}
                  initial={animations ? { opacity: 0, y: 8, scale: 0.99 } : false}
                  animate={{ opacity: 1, y: 0, scale: animations && busy && ['download', 'repair', 'upload'].includes(item.action) ? 1.012 : 1 }}
                  exit={animations ? { opacity: 0, y: -4 } : { opacity: 1 }}
                  transition={{ duration: animations ? 0.34 : 0, delay: animations ? i * 0.04 : 0, ease: [0.34, 1.3, 0.44, 1] }}>
                  {advanced
                    ? <input type="checkbox" aria-label={`选择 ${item.name}`} checked={selectedPaths.has(item.path)} onChange={() => toggle(item.path)} />
                    : <span className={`diff-dot ${item.action}`} aria-hidden="true" />}
                  <span className="diff-name">{item.name}</span><span className="diff-label">{item.label}</span>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </>}
      </section>
      <div className="manage-grid">
        <section className="card">
          <div className="card-head"><div><span className="eyebrow">ACCOUNT</span><h2>{snap.online.account?.label || '未登录'}</h2></div>
            <span className={`pill ${isDeveloper ? 'success' : ''}`}>{isDeveloper ? '开发者' : '玩家'}</span></div>
          <p className="muted">{snap.online.available ? '蓝奏云在线模块已就绪' : '在线模块未加载（可离线使用本地预设；需要云端功能请查看日志）'}</p>
          <div className="button-row">
            {snap.online.account?.label ? <button className="btn ghost" onClick={actions.logout}>退出认证</button> : <button className="btn primary" onClick={actions.login}>登录蓝奏云</button>}
          </div>
        </section>
        <section className="card">
          <div className="card-head"><div><span className="eyebrow">CLOUD</span><h2>云端来源</h2></div></div>
          {selected ? <>
            {isDeveloper && !selectedBound && <div className="create-cloud-panel">
              <div><strong>这个预设还没有云端副本</strong><span>自动创建 /PulsesSwap/{selected.name}，上传后生成分享链接。</span></div>
              <button className="btn primary" disabled={busy} onClick={() => actions.openUpload(selected.name)}>
                <Icon name="upload" size={16} />上传到云端
              </button>
            </div>}
            <label className="field">
              <span>分享链接 <Hint text="开发者发给你的一条蓝奏云链接，形如 https://wwb.lanzouq.com/b01xxxx。" /></span>
              <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="粘贴分享链接，例如 https://wwb.lanzouq.com/b01abcd" spellCheck={false} />
            </label>
            <label className="field">
              <span>提取密码 <Hint text="分享时设置的密码；没有密码就留空。" /></span>
              <div className="input-with-btn">
                <input type={showPwd ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)}
                  placeholder="没有就留空" spellCheck={false} autoComplete="off" />
                <button type="button" className="input-btn" onClick={() => setShowPwd((v) => !v)}>{showPwd ? '隐藏' : '显示'}</button>
              </div>
            </label>
            <p className="field-note">保存后会立刻检查一次云端，有新版本这里会出现「一键更新」。</p>
            {snap.online.binding?.url && <div className="share-row">
              <span>分享给玩家：</span><code title={snap.online.binding.url}>{snap.online.binding.url}</code>
              <button className="text-btn" onClick={async () => {
                try {
                  await navigator.clipboard.writeText(snap.online.binding.url)
                  actions.toast('链接已复制，发给玩家即可', 'success')
                } catch { actions.toast('复制失败，请手动选中链接', 'warning') }
              }}>复制</button>
              <Hint text="玩家在「从云端拉取预设」里粘贴这条链接就能拿到你的预设。" />
            </div>}
            <div className="button-row"><button className="btn primary" disabled={!url || !onlineReady} onClick={() => actions.bind(selected.name, url, password)}>保存绑定
                <Hint text="保存链接并自动检查一次；链接失效会提示你换一个。" /></button>
              {selectedBound && <button className="btn ghost danger-text" onClick={() => actions.unbind(selected.name)}>解除绑定
                <Hint text="取消这个预设和云端的关联；本地枪包和游戏里的文件都不会动。" /></button>}
              {advanced && <button className="btn ghost" disabled={!url} onClick={() => actions.check(selected.name)}>检查差异</button>}</div>
          </> : <p className="muted">先在主页选择一个预设</p>}
        </section>
      </div>
      <div className="manage-lower">
        <section className="card"><div className="card-head"><div><span className="eyebrow">HISTORY</span><h2>发布历史</h2></div></div>
          {(snap.online.binding?.history || []).length === 0
            ? <p className="muted pad">还没有发布记录</p>
            : (snap.online.binding.history || []).slice(0, 4).map((h, i) =>
              <div className="history-row" key={i}><strong>{h.version || 'v—'}</strong><span>{h.at ? new Date(h.at * 1000).toLocaleDateString() : ''}</span><span>上传 {h.uploaded || 0}</span></div>)}
        </section>
        <section className="card"><div className="card-head"><div><span className="eyebrow">SAFE DEFAULTS</span><h2>软件如何自动决策</h2></div></div>
          <div className="safety-lines">
            <div><strong>{isDeveloper ? '只上传变更' : '只下载必要项'}</strong><span>{isDeveloper ? '不会自动删除云端多余文件' : '删除本地多余项会进入回收站'}</span></div>
            <div><strong>自动版本</strong><span>{isDeveloper ? '在当前云端版本上递增补丁号' : '使用云端 manifest 的稳定版本'}</span></div>
            <div><strong>需要精细控制？</strong><span>在设置里开启“高级操作”</span></div>
          </div>
        </section>
      </div>
      </>}
    </div>
  )
}

function Settings({ snap, actions }) {
  const [tab, setTab] = useState('general')
  const s = snap.settings || {}
  const update = (patch) => actions.updateSettings(patch)
  return (
    <div className="page settings-page">
      <div className="page-head"><div><span className="eyebrow">PREFERENCES</span><h1>设置</h1></div>
        <span className="pill">{snap.pack.loaded ? snap.pack.name : '未加载整合包'}</span></div>
      <div className="settings-layout">
        <div className="settings-main">
          <div className="tabs" role="tablist">
            {[['general', '常规'], ['database', '数据库'], ['about', '关于']].map(([key, label]) =>
              <button key={key} role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}
          </div>
          {tab === 'general' && <div className="settings-stack">
            <section className="card"><div className="section-title"><span className="eyebrow">APPEARANCE</span><h2>外观与动效</h2></div>
              <div className="setting-row"><div><strong>界面动画 <Hint text="关掉后页面切换、弹窗都是瞬间到位，配置低的电脑更顺。" /></strong><span>关闭后所有过渡一帧到位</span></div>
                <button className={`switch ${s.animations ? 'on' : ''}`} role="switch" aria-checked={!!s.animations} aria-label="界面动画" onClick={() => update({ animations: !s.animations })}><span /></button></div>
            </section>
            <section className="card"><div className="section-title"><span className="eyebrow">IDENTITY</span><h2>身份</h2></div>
              <div className="setting-row"><div><strong>用户身份 <Hint text="开发者能上传/发布预设；玩家只能下载和替换。切身份不会丢数据。" /></strong><span>开发者可以发布到云端</span></div>
                <div className="segmented"><button className={snap.role === 'player' ? 'active' : ''} onClick={() => actions.switchRole('player')}>玩家</button>
                  <button className={snap.role === 'developer' ? 'active' : ''} onClick={() => actions.switchRole('developer')}>开发者</button></div></div>
            </section>
            <section className="card"><div className="section-title"><span className="eyebrow">OPERATION</span><h2>操作方式</h2></div>
              <div className="setting-row"><div><strong>高级操作 <Hint text="打开后才看得到勾选差异、自己填版本号和发布说明这些精细选项。" /></strong><span>手动选择差异、填写版本号和发布说明；默认关闭</span></div>
                <button className={`switch ${s.advanced_actions ? 'on' : ''}`} role="switch" aria-checked={!!s.advanced_actions} aria-label="高级操作" onClick={() => update({ advanced_actions: !s.advanced_actions })}><span /></button></div>
              {s.advanced_actions && <div className="setting-row"><div><strong>完整更新前确认</strong><span>手动模式下，批量更新前先确认差异</span></div>
                <button className={`switch ${s.online_confirm_full ? 'on' : ''}`} role="switch" aria-checked={!!s.online_confirm_full} aria-label="完整更新前确认" onClick={() => update({ online_confirm_full: !s.online_confirm_full })}><span /></button></div>}
            </section>
            <section className="card"><div className="section-title"><span className="eyebrow">SYNC</span><h2>同步偏好</h2></div>
              <div className="setting-row"><div><strong>启动时检查更新 <Hint text="打开软件时顺手看一眼云端有没有新版；只检查，不会自动下载。" /></strong><span>只检查，不下载；15 分钟内不重复</span></div>
                <button className={`switch ${s.online_auto_check ? 'on' : ''}`} role="switch" aria-checked={!!s.online_auto_check} aria-label="启动时检查更新" onClick={() => update({ online_auto_check: !s.online_auto_check })}><span /></button></div>
              <div className="setting-row"><div><strong>完全同步 <Hint text="开：云端没有的本地枪包会被删到回收站。关：本地多的文件保留不动。" /></strong><span>本地多余项进入回收站；一键更新会按此设置处理</span></div>
                <button className={`switch ${s.online_sync_clean ? 'on' : ''}`} role="switch" aria-checked={!!s.online_sync_clean} aria-label="完全同步" onClick={() => update({ online_sync_clean: !s.online_sync_clean })}><span /></button></div>
              <div className="setting-row"><div><strong>下载缓存 <Hint text="临时文件和云端下载缓存；清理不会动预设和游戏里的枪包。" /></strong><span>占用空间大或更新异常时可以清一下</span></div>
                <button className="btn small ghost" onClick={actions.clearCache}>清理缓存</button></div>
            </section>
          </div>}
          {tab === 'database' && <section className="card"><div className="section-title"><span className="eyebrow">STORAGE</span><h2>数据库</h2></div>
            <div className="info-block"><span>当前数据库</span><strong title={snap.database || ''}>{snap.database || '默认位置'}</strong></div>
            <div className="info-block"><span>存储模式</span><strong>{s.storage_mode === 'merged' ? '合并存储' : '隔离存储'}</strong></div>
            <p className="muted">切换整合包时会自动绑定对应数据库；旧版 FGC_database 会在启动时迁移。</p>
            <div className="button-row"><button className="btn ghost" onClick={actions.openDatabase}>选择数据库目录
                <Hint text="换一个文件夹放配置和缓存；切换整合包时会自动用对应的库。" /></button>
              </div>
          </section>}
          {tab === 'about' && <section className="card about"><div className="wordmark about-mark"><span className="wordmark-bar" /><span className="wordmark-pulses">Pulses</span><span className="wordmark-swap">Swap</span></div>
            <p>把 Minecraft TACZ 枪包按预设分组，一键替换，支持云端增量同步。</p>
            <p className="muted">v{snap.version} · PULSES 0 Studio · NimShade &amp; DS</p>
          </section>}
        </div>
        <aside className="settings-side">
          <section className="card"><span className="eyebrow">CURRENT</span><h2>当前工作区</h2>
            <div className="info-block"><span>整合包</span><strong>{snap.pack.name || '未选择'}</strong></div>
            <div className="info-block"><span>预设</span><strong>{snap.selected || '未选择'}</strong></div>
            <div className="info-block"><span>身份</span><strong>{snap.role === 'developer' ? '开发者' : '玩家'}</strong></div>
          </section>
          <section className="card"><span className="eyebrow">SHORTCUTS</span><h2>快捷键</h2>
            <div className="key-row"><span>快速切换页面</span><kbd>Ctrl 1-4</kbd></div>
            <div className="key-row"><span>关闭弹窗</span><kbd>Esc</kbd></div>
            <div className="key-row"><span>确认操作</span><kbd>Enter</kbd></div>
          </section>
        </aside>
      </div>
    </div>
  )
}

function LogPage({ logs, snap, onClear }) {
  const [filter, setFilter] = useState(null)
  const counts = logs.reduce((acc, l) => { acc[l.level] = (acc[l.level] || 0) + 1; return acc }, {})
  const visible = filter ? logs.filter((l) => l.level === filter) : logs
  const snapVersion = snap?.version || '3.0.0'
  const roleLabel = snap?.role === 'developer' ? '开发者' : '玩家'
  return <div className="page log-page">
    <div className="page-head"><div><span className="eyebrow">RUNTIME</span><h1>日志</h1></div>
      <div className="button-row"><span className="pill">{logs.length} 条记录</span>
        <button className="btn ghost small" disabled={!logs.length} onClick={onClear}>清空</button></div></div>
    <div className="log-layout">
      <section className="card log-card" aria-live="polite">{visible.length === 0 ? <div className="empty"><div className="empty-orbit" /><h3>{filter ? '这个级别还没有记录' : '暂无日志'}</h3><p>操作后这里会实时显示运行记录</p></div> : visible.map((l, i) =>
        <div className="log-line" key={`${l.time}-${i}`}><span className={`log-level ${l.level}`}>{l.level}</span><span className="log-time">{l.time}</span><span>{l.message}</span></div>)}
      </section>
      <aside className="log-side">
        <section className="card"><span className="eyebrow">SUMMARY</span><h2>级别统计</h2>
          <div className="log-counts">{[['SUCCESS', '成功'], ['INFO', '信息'], ['WARNING', '警告'], ['ERROR', '错误']].map(([key, label]) =>
            <div className="log-count" key={key}><span>{label}</span><strong>{counts[key] || 0}</strong></div>)}</div>
        </section>
        <section className="card"><span className="eyebrow">TIP</span><h2>日志说明</h2>
          <p className="muted small-copy">日志实时推送；完整日志包含文件扫描、云端请求和同步细节。出错时先看最后一条 ERROR。</p>
        </section>
      </aside>
    </div>
    <div className="log-lower">
      <section className="card"><span className="eyebrow">ENVIRONMENT</span><h2>运行环境</h2>
        <div className="info-block"><span>版本</span><strong>v{snapVersion}</strong></div>
        <div className="info-block"><span>身份</span><strong>{roleLabel}</strong></div>
        <div className="info-block"><span>日志条数</span><strong>{logs.length}</strong></div>
      </section>
      <section className="card"><span className="eyebrow">RECENT</span><h2>最近记录</h2>
        {logs.slice(-3).reverse().map((l, i) => <div className="mini-log" key={i}><span>{l.time}</span>{l.message}</div>)}
        {logs.length === 0 && <p className="muted">暂无记录</p>}
      </section>
      <section className="card"><span className="eyebrow">FILTER</span><h2>快速筛选</h2>
        <p className="muted small-copy">完整日志会包含 INFO 细节；日常只需关注 SUCCESS / WARNING / ERROR。</p>
        <div className="filter-chips">
          <button className={`chip success ${filter === 'SUCCESS' ? 'active' : ''}`} aria-pressed={filter === 'SUCCESS'} onClick={() => setFilter(filter === 'SUCCESS' ? null : 'SUCCESS')}>成功 {counts.SUCCESS || 0}</button>
          <button className={`chip warning ${filter === 'WARNING' ? 'active' : ''}`} aria-pressed={filter === 'WARNING'} onClick={() => setFilter(filter === 'WARNING' ? null : 'WARNING')}>警告 {counts.WARNING || 0}</button>
          <button className={`chip error ${filter === 'ERROR' ? 'active' : ''}`} aria-pressed={filter === 'ERROR'} onClick={() => setFilter(filter === 'ERROR' ? null : 'ERROR')}>错误 {counts.ERROR || 0}</button>
        </div>
      </section>
    </div>
  </div>
}

export default function App() {
  const [snap, setSnap] = useState(EMPTY)
  const [page, setPage] = useState('home')
  const [manageTab, setManageTab] = useState('overview')
  const [publishNotes, setPublishNotes] = useState('')
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState(null)
  const [toast, setToast] = useState(null)
  const [modal, setModal] = useState(null)
  const [cover, setCover] = useState({ active: false, phase: 'idle' })
  const [logs, setLogs] = useState([])
  const [dnd, setDnd] = useState(false)
  const [bridgeError, setBridgeError] = useState('')
  const jobIdRef = useRef('')
  const roleSwitchRef = useRef(false)
  const autoCheckRef = useRef('')
  const toastTimer = useRef(null)

  const lastJobRef = useRef(null)
  const autoRetryRef = useRef(0)
  const busyRef = useRef(false)
  const busyTimer = useRef(null)
  const clearBusy = useCallback(() => {
    if (busyTimer.current) { clearTimeout(busyTimer.current); busyTimer.current = null }
    busyRef.current = false
    jobIdRef.current = ''
    setBusy(null)
  }, [])
  const showToast = useCallback((message, kind = 'info', action = null) => {
    clearTimeout(toastTimer.current)
    setToast({ id: Date.now(), message, kind, action })
    toastTimer.current = setTimeout(() => setToast(null), action ? 9000 : 3200)
  }, [])

  const refresh = useCallback(async () => {
    try {
      const state = await invoke('app.bootstrap')
      setSnap(state)
      if (Array.isArray(state.logs)) setLogs(state.logs)
    } catch (err) { setBridgeError(err.message) }
  }, [])

  useEffect(() => {
    let alive = true
    const off = subscribe((event) => {
      if (!alive) return
      const type = event?.type
      if (type === 'job.progress') {
        if (jobIdRef.current && event.jobId !== jobIdRef.current) return
        if (busyTimer.current) clearTimeout(busyTimer.current)
        busyTimer.current = setTimeout(() => {
          busyRef.current = false
          setBusy(null)
          showToast('任务长时间没有响应，已自动解锁；可以重试或到日志页看原因', 'warning')
        }, 5 * 60 * 1000)
        const d = event.data || {}
        setBusy((prev) => prev ? { ...prev, progress: d.percent ?? prev.progress,
          text: d.message || prev.text, current: d.current ?? prev.current,
          total: d.total ?? prev.total, updatedAt: Date.now() } : prev)
      } else if (type === 'job.done') {
        if (jobIdRef.current && event.jobId !== jobIdRef.current) return
        const st = event.data?.result?.state
        if (st) setSnap(st)
        else refresh()
        clearBusy()
        const r = event.data?.result
        const failed = r?.result?.ok === false || r?.ok === false
        const job = lastJobRef.current
        if (!failed) autoRetryRef.current = 0
        showToast(r?.message || '操作完成', failed ? 'warning' : 'success',
          failed && job ? { label: '重试', job } : null)
      } else if (type === 'job.error') {
        if (jobIdRef.current && event.jobId !== jobIdRef.current) return
        clearBusy()
        const msg = event.data?.message || '操作失败'
        const job = lastJobRef.current
        const transient = /网络|超时|timeout|timed out|连接|Connection|ECONN|502|503|504|429/i.test(msg)
        if (transient && job && autoRetryRef.current < 1) {
          autoRetryRef.current += 1
          showToast('网络不太稳，正在自动重试…', 'info')
          setTimeout(() => startJob(job.method, job.params, job.title), 1200)
          return
        }
        autoRetryRef.current = 0
        showToast(msg, 'error', job ? { label: '重试', job } : null)
      } else if (type === 'job.cancelled') {
        if (jobIdRef.current && event.jobId !== jobIdRef.current) return
        clearBusy()
        showToast('操作已取消', 'info')
        refresh()
      } else if (type === 'state.changed') {
        if (event.data?.state) setSnap(event.data.state)
      } else if (type === 'log.append') {
        setLogs((prev) => [...prev.slice(-799), event.data])
      } else if (type === 'dnd.consumed') {
        setDnd(false)
        const jid = event.data?.jobId || event.jobId || ''
        if (jid) {
          jobIdRef.current = jid
          setBusy({ title: '拖入整合包', progress: 0, text: '正在读取拖入的整合包…', jobId: jid, cancelable: false })
        }
      } else if (type === 'dnd.error') {
        setDnd(false)
        showToast(event.data?.message || '拖入失败', 'error')
      } else if (type === 'watchdog.changed') {
        refresh()
      }
    })
    let retryTimer = null
    const tryReady = () => {
      whenReady().then((ready) => {
        if (!alive) return
        if (!ready) {
          setBridgeError('桌面桥接尚未就绪，正在重试…')
          retryTimer = setTimeout(tryReady, 900)
          return
        }
        setBridgeError('')
        if (window.PS?.dndUnavailable) showToast('当前 WebView 后端不支持拖拽，请使用“选择整合包”', 'warning')
        refresh()
      })
    }
    tryReady()
    return () => { alive = false; off(); clearTimeout(retryTimer) }
  }, [refresh, showToast])

  useEffect(() => {
    let depth = 0
    const hasFiles = (e) => Array.from(e.dataTransfer?.types || []).includes('Files')
    const enter = (e) => {
      if (!hasFiles(e)) return
      e.preventDefault()
      depth += 1
      setDnd(true)
    }
    const over = (e) => { if (hasFiles(e)) e.preventDefault() }
    const leave = () => {
      depth = Math.max(0, depth - 1)
      if (depth === 0) setDnd(false)
    }
    const drop = (e) => {
      if (hasFiles(e)) e.preventDefault()
      depth = 0; setDnd(false)
      // WebView2 的 DOM drop 在部分冷启动下不触发；直接把原生 files 交给
      // pywebview，再读回临时路径，避免拖入完全无反应。
      if (window.chrome?.webview && window.pywebview?.api?.handle_drop_pending && e.dataTransfer?.files?.length) {
        try {
          window.chrome.webview.postMessageWithAdditionalObjects('FilesDropped', e.dataTransfer.files)
          window.pywebview.api.handle_drop_pending().catch(() => {})
        } catch (_) {}
      }
    }
    window.addEventListener('dragenter', enter)
    window.addEventListener('dragover', over)
    window.addEventListener('dragleave', leave)
    window.addEventListener('drop', drop)
    return () => {
      window.removeEventListener('dragenter', enter)
      window.removeEventListener('dragover', over)
      window.removeEventListener('dragleave', leave)
      window.removeEventListener('drop', drop)
    }
  }, [])

  const prompt = useCallback((title, label, value, onConfirm) => {
    setModal({ kind: 'prompt', title, label, value, onConfirm })
  }, [])
  const confirm = useCallback((title, body, onConfirm) => {
    setModal({ kind: 'confirm', title, body, onConfirm })
  }, [])

  const startJob = useCallback(async (method, params, title) => {
    if (busyRef.current) { showToast('上一个操作还在进行，等它结束再点', 'warning'); return }
    try {
      busyRef.current = true
      lastJobRef.current = { method, params, title }
      setBusy({ title, progress: 0, text: '准备中…' })
      // 事件丢失（后端在 invoke 返回前就失败 / evaluate_js 被吞）时，最多锁 5 分钟
      if (busyTimer.current) clearTimeout(busyTimer.current)
      busyTimer.current = setTimeout(() => {
        busyRef.current = false
        setBusy(null)
        showToast('任务长时间没有响应，已自动解锁；可以重试或到日志页看原因', 'warning')
      }, 5 * 60 * 1000)
      const data = await invoke(method, params)
      jobIdRef.current = data?.jobId || ''
      setBusy((prev) => prev ? { ...prev, jobId: jobIdRef.current,
        cancelable: Boolean(data?.cancelable) } : prev)
      if (!jobIdRef.current) { clearBusy(); await refresh() }
    } catch (err) { clearBusy(); showToast(err.message, 'error') }
  }, [refresh, showToast])

  const cancelJob = useCallback(async () => {
    if (!busy?.jobId) return
    try {
      setBusy((prev) => prev ? { ...prev, text: '正在取消…' } : prev)
      await invoke('job.cancel', { jobId: busy.jobId })
    } catch (err) { showToast(err.message, 'error') }
  }, [busy?.jobId, showToast])

  useEffect(() => {
    if (!snap.pack.loaded || !snap.settings?.online_auto_check
        || !(snap.online.bound_count > 0) || autoCheckRef.current === snap.pack.path) return
    autoCheckRef.current = snap.pack.path
    startJob('online.auto.check', {}, '检查更新')
  }, [snap.pack.loaded, snap.settings?.online_auto_check,
      snap.online.bound_count, snap.pack.path, startJob])

  const openPack = useCallback((path) => startJob('pack.open', { path }, '打开整合包'), [startJob])
  const openTacz = useCallback(async () => {
    try { const data = await invoke('pack.open_tacz'); showToast('已打开 TACZ 文件夹', 'success'); return data }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])
  const clearCache = useCallback(async () => {
    try { const data = await invoke('online.clear_cache'); setSnap(data.state); showToast('缓存已清理', 'success') }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])
  const clearLogs = useCallback(async () => {
    try { const state = await invoke('app.logs.clear'); setSnap(state); setLogs([]); showToast('日志已清空', 'info') }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])
  const openDatabase = useCallback(async () => {
    try {
      const path = await pickFolder()
      if (path) startJob('db.open', { path }, '打开数据库')
    } catch (err) { showToast(err.message, 'error') }
  }, [startJob, showToast])
  const select = useCallback(async (name) => {
    try { const state = await invoke('preset.select', { name }); setSnap(state) }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])
  const createPreset = useCallback(async (name) => {
    if (!name?.trim()) throw new Error('预设名不能为空')
    try { const state = await invoke('preset.create', { name: name.trim() }); setSnap(state); showToast('预设已创建', 'success') }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])
  const rename = useCallback((item) => prompt('重命名预设', '新名称', item.name, async (v) => {
    if (!v?.trim()) throw new Error('名称不能为空')
    if (v === item.name) return
    const state = await invoke('preset.rename', { old: item.name, new: v })
    setSnap(state)
    showToast('已重命名', 'success')
  }), [prompt, showToast])
  const remove = useCallback((item) => confirm('删除预设',
    item.applied
      ? `「${item.name}」正在游戏里使用。删除会先把它从 tacz 收回，再删预设目录里的枪包（进回收站没法保证）。继续？`
      : `确定删除「${item.name}」？预设目录里的枪包会一起删除。`,
    async () => {
      try {
        if (item.applied) await invoke('preset.detach', { name: item.name })
        const state = await invoke('preset.delete', { name: item.name })
        setSnap(state)
        showToast('已删除', 'success')
      } catch (err) { showToast(err.message, 'error'); throw err }
    }), [confirm, showToast])
  const saveVersion = useCallback(async (name, version) => {
    if (!String(version || '').trim()) throw new Error('版本号不能为空')
    try { const state = await invoke('preset.version', { name, version }); setSnap(state); showToast('版本已保存', 'success') }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])
  const apply = useCallback((item) => confirm('确认替换', `将应用「${item.name}」并替换 TACZ 枪包。`, () =>
    startJob('preset.apply', { name: item.name }, '一键替换')), [confirm, startJob])

  const cloudDelete = useCallback((kind, id, name) => confirm('删除云端内容',
    `删除${kind === 'folder' ? '文件夹' : '文件'}「${name}」？云端删除不可恢复；玩家如果已经下载则不受影响。`,
    async () => {
      try {
        const out = await invoke('online.cloud.delete', { kind, id })
        setSnap(out.state)
        showToast('已删除', 'success')
      } catch (err) { showToast(err.message, 'error'); throw err }
    }), [confirm, showToast])

  const detach = useCallback((name) => confirm('收回预设', `把「${name}」从游戏里收回？枪包会回到预设目录，不会删文件。`, async () => {
    setBusy({ title: '收回预设', progress: 0, text: '正在把枪包从 tacz 拿回预设目录…' })
    try {
      const state = await invoke('preset.detach', { name })
      setSnap(state)
      showToast('已收回，可以导入或删除这个预设了', 'success')
    } catch (err) { showToast(err.message, 'error'); throw err }
    finally { setBusy(null) }
  }), [confirm, showToast])

  const reorderPresets = useCallback(async (order) => {
    if (!Array.isArray(order) || !order.length) return
    setSnap((prev) => {
      const map = new Map((prev.presets || []).map((p) => [p.name, p]))
      const next = order.map((n) => map.get(n)).filter(Boolean)
      return { ...prev, presets: next }
    })
    try {
      const state = await invoke('preset.reorder', { order })
      setSnap(state)
    } catch (err) { showToast(err.message, 'error'); refresh() }
  }, [refresh, showToast])

  const importGunpacks = useCallback(async (name) => {
    try {
      const paths = await pickFiles()
      if (!paths.length) return
      startJob('preset.import', { name, paths }, '导入枪包')
    } catch (err) { showToast(err.message, 'error') }
  }, [startJob, showToast])

  const bind = useCallback(async (name, url, password) => {
    if (!/^https?:\/\//i.test(String(url || '').trim())) {
      showToast('分享链接要以 http:// 或 https:// 开头', 'warning')
      throw new Error('链接格式不对')
    }
    try {
      const data = await invoke('online.bind', { name, url, password })
      setSnap(data.state)
      showToast('已保存绑定，正在检查云端…', 'success')
      // 绑定完自动查一次：用户不用再找"检查差异"
      startJob('online.check', { name }, '检查更新')
    } catch (err) { showToast(err.message, 'error') }
  }, [showToast, startJob])
  const check = useCallback((name) => startJob('online.check', { name }, '检查更新'), [startJob])
  const unbind = useCallback((name) => confirm('解除绑定', `解除「${name}」和云端的绑定？本地枪包不会被删。`, async () => {
    try {
      const state = await invoke('online.unbind', { name })
      setSnap(state)
      showToast('已解除绑定', 'info')
    } catch (err) { showToast(err.message, 'error'); throw err }
  }), [confirm, showToast])
  const sync = useCallback((name, selection) => startJob('online.sync', { name, selection }, '同步预设'), [startJob])
  const syncAuto = useCallback((name) => startJob('online.sync.auto', { name }, '一键更新'), [startJob])
  const publishAuto = useCallback((name, notes = '') => startJob('online.publish.auto', { name, notes }, '一键发布'), [startJob])
  const syncAllAuto = useCallback(() => startJob('online.sync.all', {}, '一键更新全部'), [startJob])
  const publishAllAuto = useCallback((notes = '') => startJob('online.publish.all', { notes }, '一键发布全部'), [startJob])
  const publishNew = useCallback((name) => startJob('online.publish.new', { name }, '上传到云端'), [startJob])
  const openUpload = useCallback((name) => {
    const preset = (snap.presets || []).find((p) => p.name === name)
    if (preset?.bound) { publishNew(name); return }        // 已绑定的走一键上传
    setModal({
      kind: 'upload', title: '上传到云端 · 首次初始化', preset,
      cloudPath: `/PulsesSwap/${name}`, version: preset?.version || 'v1.0.0', notes: '',
      confirm: '开始上传',
      onConfirm: async ({ cloud_path, version, notes }) => {
        await startJob('online.publish.new',
          { name, cloud_path, version, notes }, '上传到云端')
      },
    })
  }, [snap.presets, publishNew, startJob])
  const publishPlan = useCallback((name) => startJob('online.publish.plan', { name }, '生成发布计划'), [startJob])
  const publish = useCallback((name, version, notes, selection) => {
    if (!version?.trim()) { showToast('请填写版本号', 'warning'); return }
    startJob('online.publish.run', { name, version: version.trim(), notes, selection }, '发布预设')
  }, [startJob, showToast])
  const addFromCloud = useCallback(() => setModal({ kind: 'cloudadd', title: '从云端添加预设', confirm: '读取并创建',
    onConfirm: async ({ url, password }) => {
      if (!url?.trim()) { showToast('请填写分享链接', 'warning'); return }
      startJob('online.add', { url: url.trim(), password }, '从云端添加')
    } }), [startJob, showToast])
  const login = useCallback(() => setModal({ kind: 'login', title: '登录蓝奏云', body: '登录后才能上传/发布；只下载预设不用登录。', confirm: '登录', onConfirm: async ({ username, password }) => {
    if (!username?.trim()) throw new Error('请填写蓝奏账号（手机号或邮箱）')
    if (!password) throw new Error('请填写密码')
    const data = await invoke('account.login', { username, password })
    setSnap(data.state)
    showToast('登录成功', 'success')
  } }), [showToast])
  const logout = useCallback(async () => {
    try { const state = await invoke('account.logout'); setSnap(state); showToast('已退出认证', 'info') }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])
  const updateSettings = useCallback(async (patch) => {
    try { const state = await invoke('app.settings.update', patch); setSnap(state) }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])

  const navigate = useCallback((next) => {
    if (next === page) return
    // 页面切换只用内容区过渡，不再盖整页幕布
    setPage(next)
  }, [page])

  const openCloud = useCallback(() => {
    setManageTab('cloud')
    setPage('manage')
  }, [])

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') { setModal(null); return }
      const tag = (e.target?.tagName || '').toLowerCase()
      if (tag === 'input' || tag === 'textarea') return
      if ((e.metaKey || e.ctrlKey) && ['1', '2', '3', '4'].includes(e.key)) {
        e.preventDefault()
        const next = NAV[Number(e.key) - 1]?.key
        if (next) navigate(next)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  const switchRole = useCallback(async (role) => {
    if (role === snap.role || roleSwitchRef.current) return
    if (role === 'developer' && !snap.online.account?.label) {
      login()
      return
    }
    roleSwitchRef.current = true
    const label = role === 'developer' ? '开发者' : '玩家'
    const animate = snap.settings?.animations !== false
    if (animate) setCover({ active: true, phase: 'role-cover', note: `正在切换为${label}`, target: role })
    try {
      const state = await invoke('app.role.switch', { role })
      if (!animate) { setSnap(state); }
      else {
        // 至少让渐变铺开，再在覆盖层下换主题
        await new Promise((r) => setTimeout(r, 320))
        setSnap(state)
        setCover((s) => ({ ...s, phase: 'role-hold', note: `已切换为${label}` }))
        await new Promise((r) => setTimeout(r, 380))
        setCover((s) => ({ ...s, phase: 'role-reveal' }))
        await new Promise((r) => setTimeout(r, 520))
        setCover({ active: false, phase: 'idle' })
      }
      showToast(role === 'developer' ? '已切换为开发者' : '已切换为玩家', 'success')
    } catch (err) {
      setCover({ active: false, phase: 'idle' })
      showToast(err.message, 'error')
    } finally {
      roleSwitchRef.current = false
    }
  }, [snap.role, snap.online.account?.label, snap.settings?.animations, login, showToast])

  const openPresetDetail = useCallback(async (preset) => {
    setModal({
      kind: 'preset', title: '预设详情', preset, details: null,
      confirm: '保存修改',
      onConfirm: async (payload) => {
        if (!payload.name) { showToast('预设名不能为空', 'error'); return }
        try {
          let state = null
          if (payload.name !== preset.name) {
            state = await invoke('preset.rename', { old: preset.name, new: payload.name })
          }
          if (payload.version && payload.version !== preset.version) {
            state = await invoke('preset.version', {
              name: payload.name || preset.name, version: payload.version,
            })
          }
          if (state) setSnap(state)
          else await refresh()
          showToast('预设已保存', 'success')
        } catch (err) { showToast(err.message, 'error') }
      },
    })
    try {
      const details = await invoke('preset.details', { name: preset.name })
      setModal((m) => m?.kind === 'preset' && m.preset?.name === preset.name
        ? { ...m, details } : m)
    } catch (err) {
      showToast(err.message, 'error')
      setModal((m) => (m?.kind === 'preset' && m.preset?.name === preset.name
        ? { ...m, details: { error: err.message } } : m))
    }
  }, [refresh, showToast])
  const actions = { openPack, openCloud, startJob, reorderPresets, detach, cloudDelete, openTacz, clearCache, clearLogs, addFromCloud, openDatabase, select, createPreset, rename, delete: remove, saveVersion, apply, bind, unbind, check, sync, syncAuto, publishAuto, syncAllAuto, publishAllAuto, publishNew, openUpload, publishPlan, publish, login, logout, updateSettings, switchRole, prompt, toast: showToast, navigate, cancelJob, presetDetails: openPresetDetail, importGunpacks }
  const animations = snap.settings?.animations !== false
  const pageEl = page === 'home' ? <Home snap={snap} actions={actions} busy={busy} publishNotes={publishNotes} />
    : page === 'manage' ? <Manage snap={snap} actions={actions} busy={busy} tab={manageTab} onTab={setManageTab} publishNotes={publishNotes} setPublishNotes={setPublishNotes} />
    : page === 'settings' ? <Settings snap={snap} actions={actions} />
    : <LogPage logs={logs} snap={snap} onClear={clearLogs} />

  return (
    <div className={`app role-${snap.role} ${expanded ? 'sidebar-open' : ''} ${snap.settings?.animations === false ? 'animations-off' : ''}`}>
      <Sidebar page={page} onNavigate={navigate} role={snap.role} loggedIn={Boolean(snap.online.account?.label)} expanded={expanded} setExpanded={setExpanded} version={snap.version} onSwitchRole={() => actions.switchRole(snap.role === 'developer' ? 'player' : 'developer')} pack={snap.pack} presetCount={snap.presets.length} />
      <main className="workspace">
        <div className="content">
          <AnimatePresence mode="wait" initial={false}>
            <motion.div key={page} className="page-motion"
              initial={animations ? { opacity: 0, y: 6 } : false}
              animate={{ opacity: 1, y: 0 }}
              exit={animations ? { opacity: 0, y: -4 } : { opacity: 1 }}
              transition={{ duration: animations ? 0.18 : 0 }}>
              {pageEl}
            </motion.div>
          </AnimatePresence>
          {bridgeError && <div className="bridge-error">{bridgeError}</div>}
          {dnd && <div className="drop-overlay"><div className="drop-inner"><Icon name="download" size={28} /><h2>松手导入</h2><p>拖入整合包文件夹，自动定位 tacz</p></div></div>}
          <Toast toast={toast} onAction={(action) => {
            if (action?.job) {
              const { method, params, title } = action.job
              startJob(method, params, title)
            }
          }} />
          <AnimatePresence>{busy && <div className="busy-toast"><Progress value={busy.progress} text={busy.text || busy.title} />
            <button className="btn small ghost cancel-job" disabled={!busy.jobId || !busy.cancelable} onClick={actions.cancelJob}>取消</button></div>}</AnimatePresence>
        </div>
        <footer className="statusbar">
          <span className={`status-dot ${snap.pack.loaded ? 'ready' : ''}`} />
          <span>{busy ? (busy.text || busy.title) : (snap.pack.loaded ? '工作区就绪' : '等待加载整合包')}</span>
          <span className="statusbar-meta">{snap.role === 'developer' ? '开发者' : '玩家'} · {snap.pack.name || '未选择整合包'}</span>
        </footer>
      </main>
      <Cover state={cover} />
      <JobBar busy={busy} onCancel={cancelJob} />
      <Modal modal={modal} onClose={() => setModal(null)} />
    </div>
  )
}
