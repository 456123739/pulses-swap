import React, { useCallback, useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import Icon from './components/Icons.jsx'
import { hasBridge, invoke, pickFolder, subscribe, whenReady } from './bridge.js'

const EMPTY = {
  version: '', role: 'player',
  pack: { path: '', name: '', tacz: '', loaded: false },
  presets: [], selected: null, gunpacks: [], plan: null,
  online: { available: false, account: {}, binding: {} },
  settings: {}, recent: [], logs: [], capabilities: {},
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
    <div className={`cover cover-${state.phase}`} aria-hidden="true">
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

function Sidebar({ page, onNavigate, role, expanded, setExpanded, version }) {
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
      <div className="sidebar-foot">
        <span className={`role-dot ${role}`} />
        <span>{role === 'developer' ? '开发者' : '玩家'}</span>
      </div>
    </aside>
  )
}

function Modal({ modal, onClose }) {
  const [value, setValue] = useState(modal?.value || '')
  const [password, setPassword] = useState('')
  const submitted = useRef(false)
  const cardRef = useRef(null)
  const previousFocus = useRef(null)
  useEffect(() => {
    setValue(modal?.value || ''); setPassword(''); submitted.current = false
    if (!modal) return undefined
    previousFocus.current = document.activeElement
    const timer = setTimeout(() => cardRef.current?.focus(), 0)
    return () => { clearTimeout(timer); previousFocus.current?.focus?.() }
  }, [modal])
  if (!modal) return null
  const submit = () => {
    if (submitted.current) return
    submitted.current = true
    const callback = modal.onConfirm
    const payload = modal.kind === 'login' ? { username: value, password } : value
    onClose()
    Promise.resolve(callback(payload)).catch(() => {})
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
        <div className="modal-actions">
          <button className="btn ghost" onClick={onClose}>取消</button>
          <button className="btn primary" onClick={submit}>{modal.confirm || '确定'}</button>
        </div>
      </motion.div>
    </div>
  )
}

function Toast({ toast }) {
  return (
    <AnimatePresence>
      {toast && (
        <motion.div key={toast.id} className={`toast ${toast.kind || 'info'}`} role="status" aria-live="polite"
          initial={{ opacity: 0, x: 30, scale: 0.97 }} animate={{ opacity: 1, x: 0, scale: 1 }}
          exit={{ opacity: 0, x: 20, scale: 0.98 }} transition={{ type: 'spring', stiffness: 420, damping: 32 }}>
          <span className="toast-dot" />{toast.message}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function Empty({ title, hint, children }) {
  return <div className="empty"><div className="empty-orbit" /><h3>{title}</h3>{hint && <p>{hint}</p>}{children}</div>
}

function PresetRow({ item, selected, onSelect, onRename, onDelete }) {
  return (
    <div className={`preset-row ${selected ? 'selected' : ''}`} onClick={() => onSelect(item.name)}>
      <div className="preset-main">
        <strong>{item.name}</strong>
        <span>{item.version || 'v1.0.0'} · {item.count || 0} 个枪包</span>
      </div>
      {item.applied && <span className="pill success">已应用</span>}
      <div className="row-actions" onClick={(e) => e.stopPropagation()}>
        <button className="text-btn" onClick={() => onRename(item)}>重命名</button>
        <button className="text-btn danger" onClick={() => onDelete(item)}>删除</button>
      </div>
    </div>
  )
}

function Home({ snap, actions, busy }) {
  const selected = snap.presets.find((p) => p.name === snap.selected)
  const animations = snap.settings?.animations !== false
  const [celebrate, setCelebrate] = useState(false)
  const wasApplied = useRef(Boolean(selected?.applied))
  const lastName = useRef(selected?.name)
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
    try {
      const path = await pickFolder()
      if (path) actions.openPack(path)
    } catch (err) { actions.toast(err.message, 'error') }
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

      {!snap.pack.loaded ? (
        <>
          <motion.section className="home-hero empty-hero" aria-label="导入整合包"
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
            <div className="hero-actions">
              <button className="btn hero-primary" onClick={openPack}><Icon name="folder" size={21} />选择整合包</button>
              <span className="drop-caption">或把文件夹直接拖进来</span>
            </div>
          </motion.section>
          <div className="home-grid empty-home-grid">
            <section className="card presets-card">
              <div className="card-head"><div><span className="eyebrow">PRESETS</span><h2>预设 <span className="count-badge">0</span></h2></div>
                <button className="btn small" disabled><Icon name="plus" />新建</button></div>
              <div className="empty-list"><Icon name="folder" size={22} /><strong>导入后自动生成</strong><span>整合包里的 tacz 会被识别为第一个预设。</span></div>
            </section>
            <section className="card detail-card">
              <div className="card-head"><div><span className="eyebrow">DETAIL</span><h2>等待整合包</h2></div></div>
              <div className="empty-list"><Icon name="download" size={22} /><strong>拖入即可开始</strong><span>预设、枪包列表和云端绑定会显示在这里。</span></div>
              {snap.recent?.length > 0 && <div className="recent-strip">
                <span className="eyebrow">最近</span>
                {snap.recent.slice(0, 3).map((r) => <button key={r.path} className="recent-chip" onClick={() => actions.openPack(r.path)} title={r.path}>{r.name || r.path}</button>)}
              </div>}
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
              </div>
            </motion.div>
            <div className="hero-actions">
              <button className={`btn hero-primary ${celebrate ? 'is-applied' : ''}`} disabled={!selected || busy}
                onClick={() => selected && actions.apply(selected)}>
                <Icon name="check" size={21} />{celebrate ? '已应用' : (selected?.applied ? '重新替换' : '一键替换')}
              </button>
              {(snap.online.bound_count || 0) > 0
                ? <button className="btn hero-secondary" disabled={busy}
                    onClick={() => snap.role === 'player' ? actions.syncAllAuto() : actions.publishAllAuto()}>
                    <Icon name={snap.role === 'player' ? 'cloud' : 'upload'} size={17} />
                    {snap.role === 'player' ? '一键更新全部' : '一键上传全部'}
                  </button>
                : <button className="btn hero-secondary" onClick={openPack}>
                    <Icon name="folder" size={17} />选择整合包
                  </button>}
            </div>
            {busy && <div className="hero-progress"><Progress value={busy.progress} text={busy.text || busy.title} /></div>}
          </motion.section>

          <div className="home-grid">
            <section className="card presets-card">
              <div className="card-head">
                <div><span className="eyebrow">PRESETS</span><h2>预设 <span className="count-badge">{snap.presets.length}</span></h2></div>
                <button className="btn small" onClick={() => actions.prompt('新建预设', '名称', '', (v) => actions.createPreset(v))}><Icon name="plus" />新建</button>
              </div>
              <div className="preset-list">
                {snap.presets.length === 0 ? <p className="muted pad">还没有预设</p> : snap.presets.map((p) => (
                  <PresetRow key={p.name} item={p} selected={p.name === snap.selected}
                    onSelect={actions.select} onRename={actions.rename} onDelete={actions.delete} />
                ))}
              </div>
            </section>

            <motion.section className="card detail-card" key={selected?.name || 'none'}
              initial={animations ? { opacity: 0, y: 7 } : false} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: animations ? 0.28 : 0, ease: [0.22, 1, 0.36, 1] }}>
              <div className="card-head"><div><span className="eyebrow">DETAIL</span><h2>{selected?.name || '未选择'}</h2></div>
                {selected && <span className={`pill ${selected.applied ? 'success' : ''}`}>{selected.applied ? '已应用' : '未应用'}</span>}</div>
              {selected ? <>
                <div className="detail-row"><span>版本</span><strong>{selected.version}</strong>
                  <button className="text-btn" onClick={() => actions.prompt('修改版本号', '版本号', selected.version, (v) => actions.saveVersion(selected.name, v))}>修改</button></div>
                <div className="detail-row"><span>云端</span><strong>{snap.online.binding?.url ? '已绑定' : '未绑定'}</strong></div>
                <div className="gunpack-head"><span>枪包列表</span><span className="muted">共 {snap.gunpacks.length} 个</span></div>
                <div className="gunpack-list">
                  {snap.gunpacks.length === 0 ? <p className="muted pad">这个预设还没有枪包</p> : (
                    <AnimatePresence mode="popLayout" initial={false}>
                      {snap.gunpacks.map((g, i) => (
                        <motion.div className="gunpack-row" key={`${snap.selected}:${g.name}`}
                          initial={animations ? { opacity: 0, y: 10 } : false}
                          animate={{ opacity: 1, y: 0 }}
                          exit={animations ? { opacity: 0, y: -4 } : { opacity: 1 }}
                          transition={{ duration: animations ? 0.4 : 0, delay: animations ? i * 0.045 : 0, ease: [0.34, 1.3, 0.44, 1] }}>
                          <Icon name="folder" size={15} /><span>{g.name}</span>
                          <span className="muted">{g.type || 'zip'}</span>
                        </motion.div>
                      ))}
                    </AnimatePresence>
                  )}
                </div>
                <div className="detail-footer">
                  <span className="muted">{snap.online.binding?.url ? '云端已绑定，可增量同步' : '尚未绑定云端来源'}</span>
                  <button className="btn ghost small" onClick={() => actions.navigate('manage')}>管理云端</button>
                </div>
              </> : <div className="detail-empty"><p>从左侧选择一个预设</p><span>选中后可在这里查看版本、云端绑定和枪包列表。</span></div>}
            </motion.section>
          </div>
        </>
      )}
    </div>
  )
}

function Manage({ snap, actions, busy }) {
  const animations = snap.settings?.animations !== false
  const advanced = snap.settings?.advanced_actions === true
  const [url, setUrl] = useState(snap.online.binding?.url || '')
  const [password, setPassword] = useState(snap.online.binding?.password || '')
  const [selection, setSelection] = useState(null)
  const [publishVersion, setPublishVersion] = useState('')
  const [publishNotes, setPublishNotes] = useState('')
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
      <section className="action-deck manage-action" aria-label="管理主要操作">
        <div className="action-copy">
          <span className="eyebrow">ONE CLICK</span>
          <h2>全部云端预设 · {boundCount} 个</h2>
          <p>{boundCount ? autoHint : '还没有绑定云端来源；先选择一个预设并保存分享链接。'}</p>
          <div className="action-meta">
            <span>{boundCount} 个已绑定</span>
            <span>{plan?.summary || (isDeveloper ? '待上传检查' : '待更新检查')}</span>
            <span>{isDeveloper ? '开发者' : '玩家'}</span>
          </div>
        </div>
        <div className="action-buttons">
          <button className="btn xl primary action-primary" disabled={!boundCount || busy}
            onClick={runAuto}><Icon name={isDeveloper ? 'upload' : 'cloud'} size={20} />{autoLabel}</button>
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
      <section className="card plan-card">
        <div className="card-head"><div><span className="eyebrow">DIFF</span><h2>{isDeveloper ? '待上传差异' : '云端差异'}</h2></div>
          {plan && <span className="pill">{plan.summary}</span>}</div>
        {planMismatch ? <p className="auto-note warning-note">当前差异计划属于另一个身份，已隐藏；点上方“{autoLabel}”会按当前身份重新计算。</p>
          : !plan ? <p className="muted pad">不需要手动检查。点上方“{autoLabel}”，软件会逐个比对所有已绑定预设并完成操作。</p> : <>
          {advanced && isDeveloper && <div className="publish-row">
            <label className="field"><span>发布版本号</span><input value={publishVersion} onChange={(e) => setPublishVersion(e.target.value)} placeholder={selected?.version || 'v1.0.0'} /></label>
            <label className="field"><span>发布说明</span><input value={publishNotes} onChange={(e) => setPublishNotes(e.target.value)} placeholder="可选" /></label>
          </div>}
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
          <p className="muted">{snap.online.available ? '蓝奏云在线模块已就绪' : '在线模块不可用'}</p>
          <div className="button-row">
            {snap.online.account?.label ? <button className="btn ghost" onClick={actions.logout}>退出认证</button> : <button className="btn primary" onClick={actions.login}>登录蓝奏云</button>}
          </div>
        </section>
        <section className="card">
          <div className="card-head"><div><span className="eyebrow">CLOUD</span><h2>云端来源</h2></div></div>
          {selected ? <>
            <label className="field"><span>分享链接</span><input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://..." /></label>
            <label className="field"><span>提取密码</span><input value={password} onChange={(e) => setPassword(e.target.value)} placeholder="可留空" /></label>
            <div className="button-row"><button className="btn primary" disabled={!url} onClick={() => actions.bind(selected.name, url, password)}>保存绑定</button>
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
              <div className="setting-row"><div><strong>界面动画</strong><span>关闭后所有过渡一帧到位</span></div>
                <button className={`switch ${s.animations ? 'on' : ''}`} role="switch" aria-checked={!!s.animations} aria-label="界面动画" onClick={() => update({ animations: !s.animations })}><span /></button></div>
            </section>
            <section className="card"><div className="section-title"><span className="eyebrow">IDENTITY</span><h2>身份</h2></div>
              <div className="setting-row"><div><strong>用户身份</strong><span>开发者可以发布到云端</span></div>
                <div className="segmented"><button className={snap.role === 'player' ? 'active' : ''} onClick={() => actions.switchRole('player')}>玩家</button>
                  <button className={snap.role === 'developer' ? 'active' : ''} onClick={() => actions.switchRole('developer')}>开发者</button></div></div>
            </section>
            <section className="card"><div className="section-title"><span className="eyebrow">OPERATION</span><h2>操作方式</h2></div>
              <div className="setting-row"><div><strong>高级操作</strong><span>手动选择差异、填写版本号和发布说明；默认关闭</span></div>
                <button className={`switch ${s.advanced_actions ? 'on' : ''}`} role="switch" aria-checked={!!s.advanced_actions} aria-label="高级操作" onClick={() => update({ advanced_actions: !s.advanced_actions })}><span /></button></div>
              {s.advanced_actions && <div className="setting-row"><div><strong>完整更新前确认</strong><span>手动模式下，批量更新前先确认差异</span></div>
                <button className={`switch ${s.online_confirm_full ? 'on' : ''}`} role="switch" aria-checked={!!s.online_confirm_full} aria-label="完整更新前确认" onClick={() => update({ online_confirm_full: !s.online_confirm_full })}><span /></button></div>}
            </section>
            <section className="card"><div className="section-title"><span className="eyebrow">SYNC</span><h2>同步偏好</h2></div>
              <div className="setting-row"><div><strong>启动时检查更新</strong><span>只检查，不自动下载</span></div>
                <button className={`switch ${s.online_auto_check ? 'on' : ''}`} role="switch" aria-checked={!!s.online_auto_check} aria-label="启动时检查更新" onClick={() => update({ online_auto_check: !s.online_auto_check })}><span /></button></div>
              <div className="setting-row"><div><strong>完全同步</strong><span>本地多余项进入回收站；一键更新会按此设置处理</span></div>
                <button className={`switch ${s.online_sync_clean ? 'on' : ''}`} role="switch" aria-checked={!!s.online_sync_clean} aria-label="完全同步" onClick={() => update({ online_sync_clean: !s.online_sync_clean })}><span /></button></div>
            </section>
          </div>}
          {tab === 'database' && <section className="card"><div className="section-title"><span className="eyebrow">STORAGE</span><h2>数据库</h2></div>
            <div className="info-block"><span>当前数据库</span><strong>{snap.pack.path || '未绑定整合包'}</strong></div>
            <div className="info-block"><span>存储模式</span><strong>{s.storage_mode === 'merged' ? '合并存储' : '隔离存储'}</strong></div>
            <p className="muted">切换整合包时会自动绑定对应数据库；旧版 FGC_database 会在启动时迁移。</p>
            <button className="btn ghost" onClick={actions.openDatabase}>选择数据库目录</button>
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

function LogPage({ logs, snap }) {
  const counts = logs.reduce((acc, l) => { acc[l.level] = (acc[l.level] || 0) + 1; return acc }, {})
  const snapVersion = snap?.version || '3.0.0'
  const roleLabel = snap?.role === 'developer' ? '开发者' : '玩家'
  return <div className="page log-page">
    <div className="page-head"><div><span className="eyebrow">RUNTIME</span><h1>日志</h1></div>
      <span className="pill">{logs.length} 条记录</span></div>
    <div className="log-layout">
      <section className="card log-card" aria-live="polite">{logs.length === 0 ? <div className="empty"><div className="empty-orbit" /><h3>暂无日志</h3><p>操作后这里会实时显示运行记录</p></div> : logs.map((l, i) =>
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
        <div className="filter-chips"><span className="chip success">成功 {counts.SUCCESS || 0}</span><span className="chip warning">警告 {counts.WARNING || 0}</span><span className="chip error">错误 {counts.ERROR || 0}</span></div>
      </section>
    </div>
  </div>
}

export default function App() {
  const [snap, setSnap] = useState(EMPTY)
  const [page, setPage] = useState('home')
  const [expanded, setExpanded] = useState(false)
  const [busy, setBusy] = useState(null)
  const [toast, setToast] = useState(null)
  const [modal, setModal] = useState(null)
  const [cover, setCover] = useState({ active: false, phase: 'idle' })
  const [logs, setLogs] = useState([])
  const [dnd, setDnd] = useState(false)
  const [bridgeError, setBridgeError] = useState('')
  const jobIdRef = useRef('')
  const coverTimers = useRef([])
  const roleSwitchRef = useRef(false)
  const toastTimer = useRef(null)

  const showToast = useCallback((message, kind = 'info') => {
    clearTimeout(toastTimer.current)
    setToast({ id: Date.now(), message, kind })
    toastTimer.current = setTimeout(() => setToast(null), 3200)
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
        if (event.jobId !== jobIdRef.current) return
        const d = event.data || {}
        setBusy((prev) => prev ? { ...prev, progress: d.percent ?? prev.progress, text: d.message || prev.text } : prev)
      } else if (type === 'job.done') {
        if (event.jobId !== jobIdRef.current) return
        const st = event.data?.result?.state
        if (st) setSnap(st)
        else refresh()
        setBusy(null)
        const r = event.data?.result
        const failed = r?.result?.ok === false || r?.ok === false
        showToast(r?.message || '操作完成', failed ? 'warning' : 'success')
      } else if (type === 'job.error') {
        if (event.jobId !== jobIdRef.current) return
        setBusy(null)
        showToast(event.data?.message || '操作失败', 'error')
      } else if (type === 'job.cancelled') {
        if (event.jobId !== jobIdRef.current) return
        setBusy(null)
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
    const drop = (e) => { if (hasFiles(e)) e.preventDefault(); depth = 0; setDnd(false) }
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
    try {
      setBusy({ title, progress: 0, text: '准备中…' })
      const data = await invoke(method, params)
      jobIdRef.current = data?.jobId || ''
      setBusy((prev) => prev ? { ...prev, jobId: jobIdRef.current,
        cancelable: Boolean(data?.cancelable) } : prev)
      if (!jobIdRef.current) { setBusy(null); await refresh() }
    } catch (err) { setBusy(null); showToast(err.message, 'error') }
  }, [refresh, showToast])

  const cancelJob = useCallback(async () => {
    if (!busy?.jobId) return
    try {
      setBusy((prev) => prev ? { ...prev, text: '正在取消…' } : prev)
      await invoke('job.cancel', { jobId: busy.jobId })
    } catch (err) { showToast(err.message, 'error') }
  }, [busy?.jobId, showToast])

  const openPack = useCallback((path) => startJob('pack.open', { path }, '打开整合包'), [startJob])
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
    if (!name?.trim()) return
    try { const state = await invoke('preset.create', { name: name.trim() }); setSnap(state); showToast('预设已创建', 'success') }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])
  const rename = useCallback((item) => prompt('重命名预设', '新名称', item.name, async (v) => {
    if (!v || v === item.name) return
    try { const state = await invoke('preset.rename', { old: item.name, new: v }); setSnap(state); showToast('已重命名', 'success') }
    catch (err) { showToast(err.message, 'error') }
  }), [prompt, showToast])
  const remove = useCallback((item) => confirm('删除预设', `确定删除「${item.name}」？`, async () => {
    try { const state = await invoke('preset.delete', { name: item.name }); setSnap(state); showToast('已删除', 'success') }
    catch (err) { showToast(err.message, 'error') }
  }), [confirm, showToast])
  const saveVersion = useCallback(async (name, version) => {
    try { const state = await invoke('preset.version', { name, version }); setSnap(state); showToast('版本已保存', 'success') }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])
  const apply = useCallback((item) => confirm('确认替换', `将应用「${item.name}」并替换 TACZ 枪包。`, () =>
    startJob('preset.apply', { name: item.name }, '一键替换')), [confirm, startJob])

  const bind = useCallback(async (name, url, password) => {
    try { const data = await invoke('online.bind', { name, url, password }); setSnap(data.state); showToast('已保存云端绑定', 'success') }
    catch (err) { showToast(err.message, 'error') }
  }, [showToast])
  const check = useCallback((name) => startJob('online.check', { name }, '检查更新'), [startJob])
  const sync = useCallback((name, selection) => startJob('online.sync', { name, selection }, '同步预设'), [startJob])
  const syncAuto = useCallback((name) => startJob('online.sync.auto', { name }, '一键更新'), [startJob])
  const publishAuto = useCallback((name) => startJob('online.publish.auto', { name }, '一键发布'), [startJob])
  const syncAllAuto = useCallback(() => startJob('online.sync.all', {}, '一键更新全部'), [startJob])
  const publishAllAuto = useCallback(() => startJob('online.publish.all', {}, '一键发布全部'), [startJob])
  const publishPlan = useCallback((name) => startJob('online.publish.plan', { name }, '生成发布计划'), [startJob])
  const publish = useCallback((name, version, notes, selection) => {
    if (!version?.trim()) { showToast('请填写版本号', 'warning'); return }
    startJob('online.publish.run', { name, version: version.trim(), notes, selection }, '发布预设')
  }, [startJob, showToast])
  const login = useCallback(() => setModal({ kind: 'login', title: '登录蓝奏云', onConfirm: async ({ username, password }) => {
    try { const data = await invoke('account.login', { username, password }); setSnap(data.state); showToast('登录成功', 'success') }
    catch (err) { showToast(err.message, 'error') }
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
    if (next === page || cover.active) return
    if (snap.settings?.animations === false) { setPage(next); return }
    setCover({ active: true, phase: 'cover', note: `正在打开${NAV.find((n) => n.key === next)?.label || ''}` })
    clearTimeout(coverTimers.current[0]); clearTimeout(coverTimers.current[1]); clearTimeout(coverTimers.current[2])
    coverTimers.current[0] = setTimeout(() => { setPage(next); setCover((s) => ({ ...s, phase: 'hold' })) }, 250)
    coverTimers.current[1] = setTimeout(() => setCover((s) => ({ ...s, phase: 'reveal' })), 770)
    coverTimers.current[2] = setTimeout(() => setCover({ active: false, phase: 'idle' }), 1150)
  }, [page, cover.active, snap.settings?.animations])

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
    if (role === snap.role || cover.active || roleSwitchRef.current) return
    if (snap.settings?.animations === false) {
      roleSwitchRef.current = true
      try {
        const state = await invoke('app.role.switch', { role })
        setSnap(state)
        showToast(role === 'developer' ? '已切换为开发者' : '已切换为玩家', 'success')
      } catch (err) { showToast(err.message, 'error') }
      roleSwitchRef.current = false
      return
    }
    roleSwitchRef.current = true
    setCover({ active: true, phase: 'cover', note: role === 'developer' ? '正在切换为开发者' : '正在切换为玩家' })
    await new Promise((r) => setTimeout(r, 250))
    setCover((s) => ({ ...s, phase: 'hold' }))
    try { const state = await invoke('app.role.switch', { role }); setSnap(state); showToast(role === 'developer' ? '已切换为开发者' : '已切换为玩家', 'success') }
    catch (err) { showToast(err.message, 'error') }
    await new Promise((r) => setTimeout(r, 520))
    setCover((s) => ({ ...s, phase: 'reveal' }))
    await new Promise((r) => setTimeout(r, 380))
    roleSwitchRef.current = false
    setCover({ active: false, phase: 'idle' })
  }, [snap.role, cover.active, snap.settings?.animations, showToast])

  const actions = { openPack, openDatabase, select, createPreset, rename, delete: remove, saveVersion, apply, bind, check, sync, syncAuto, publishAuto, syncAllAuto, publishAllAuto, publishPlan, publish, login, logout, updateSettings, switchRole, prompt, toast: showToast, navigate, cancelJob }
  const animations = snap.settings?.animations !== false
  const pageEl = page === 'home' ? <Home snap={snap} actions={actions} busy={busy} />
    : page === 'manage' ? <Manage snap={snap} actions={actions} busy={busy} />
    : page === 'settings' ? <Settings snap={snap} actions={actions} />
    : <LogPage logs={logs} snap={snap} />

  return (
    <div className={`app role-${snap.role} ${expanded ? 'sidebar-open' : ''} ${snap.settings?.animations === false ? 'animations-off' : ''}`}>
      <Sidebar page={page} onNavigate={(next) => { setExpanded(false); navigate(next) }} role={snap.role} expanded={expanded} setExpanded={setExpanded} version={snap.version} />
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
          <Toast toast={toast} />
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
      <Modal modal={modal} onClose={() => setModal(null)} />
    </div>
  )
}
