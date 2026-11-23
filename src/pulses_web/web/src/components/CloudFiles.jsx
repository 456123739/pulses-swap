import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Icon from './Icons.jsx'
import Hint from './Hint.jsx'
import { invoke, pickFiles } from '../bridge.js'

/** 云端盘：按真实网盘结构浏览 / 搜索 / 上传 / 分享 / 删除，尽量接近网页版。 */
export default function CloudFiles({ snap, actions, busy }) {
  const [path, setPath] = useState('/')
  const [data, setData] = useState(null)
  const [tree, setTree] = useState({})            // path -> folders
  const [expanded, setExpanded] = useState({ '/': true })
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [quota, setQuota] = useState(null)
  const [updatedAt, setUpdatedAt] = useState('')
  const [auto, setAuto] = useState(true)
  const [peek, setPeek] = useState(null)
  const accountOk = Boolean(snap.online.account?.label) && snap.online.available !== false

  const load = useCallback(async (target, quiet = false) => {
    if (!accountOk) return
    if (!quiet) setLoading(true)
    setError('')
    try {
      const out = await invoke('online.cloud.browse', { path: target })
      setData(out); setPath(out?.path || target)
      setTree((prev) => ({ ...prev, [out?.path || target]: out.folders || [] }))
      setUpdatedAt(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
    } catch (err) {
      setError(err.message)
      if (!quiet) setData(null)
    } finally { setLoading(false) }
  }, [accountOk])

  const loadQuota = useCallback(() => {
    if (!accountOk) return
    invoke('online.cloud.quota').then((out) => setQuota(out?.quota || null)).catch(() => {})
  }, [accountOk])

  useEffect(() => { load('/') ; loadQuota() }, [load, loadQuota])
  useEffect(() => {
    const partsNow = path.split('/').filter(Boolean)
    const nodes = ['/', ...partsNow.map((_, i) => '/' + partsNow.slice(0, i + 1).join('/'))]
    setExpanded((prev) => {
      const next = { ...prev }
      nodes.slice(0, -1).forEach((n) => { next[n] = true })
      return next
    })
    nodes.slice(0, -1).forEach(async (n) => {
      if (tree[n]) return
      try {
        const out = await invoke('online.cloud.browse', { path: n })
        setTree((prev) => (prev[n] ? prev : { ...prev, [n]: out.folders || [] }))
      } catch { /* ignore */ }
    })
  }, [path, tree])
  useEffect(() => { if (auto && accountOk) { const t = setInterval(() => { if (!document.hidden) load(path, true) }, 20000); return () => clearInterval(t) } return undefined }, [auto, path, accountOk, load])
  useEffect(() => { if (snap.revision) load(path, true) }, [snap.revision])

  const full = (name) => `${path.replace(/\/$/, '')}/${name}`.replace(/\/+/g, '/')
  const parts = path.split('/').filter(Boolean)
  const folders = data?.folders || []
  const files = data?.files || []
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return {
      folders: q ? folders.filter((f) => f.name.toLowerCase().includes(q)) : folders,
      files: q ? files.filter((f) => f.name.toLowerCase().includes(q)) : files,
    }
  }, [folders, files, query])

  const toggleTree = async (nodePath) => {
    const next = !expanded[nodePath]
    setExpanded((prev) => ({ ...prev, [nodePath]: next }))
    if (next && !tree[nodePath]) {
      try { const out = await invoke('online.cloud.browse', { path: nodePath })
        setTree((prev) => ({ ...prev, [nodePath]: out.folders || [] }))
      } catch { /* 没权限/已删除的目录忽略 */ }
    }
  }

  const copyShare = async (target) => {
    try {
      const out = await invoke('online.cloud.share', { path: target })
      const share = out?.share || {}
      const text = share.password ? `${share.url}  密码：${share.password}` : share.url
      await navigator.clipboard?.writeText(text)
      actions.toast(share.password ? '分享链接已复制（含密码）' : '分享链接已复制', 'success')
    } catch (err) { actions.toast(err.message, 'error') }
  }

  const upload = async () => {
    try {
      const paths = await pickFiles()
      if (!paths.length) return
      actions.startJob('online.cloud.upload', { path, paths }, '上传云端文件')
    } catch (err) { actions.toast(err.message, 'error') }
  }
  const mkdir = () => actions.prompt('新建云端文件夹', '文件夹名', '', async (name) => {
    if (!name?.trim()) throw new Error('文件夹名不能为空')
    await invoke('online.cloud.mkdir', { parent: path, name: name.trim() })
    actions.toast('已新建文件夹', 'success')
    await load(path)
  })

  if (!accountOk) {
    return <section className="card cloud-panel"><div className="empty"><div className="empty-orbit" />
      <h3>先登录蓝奏云</h3><p>登录后就能在软件里管理云端文件，不用再开浏览器。</p>
      <button className="btn primary" onClick={actions.login}>登录蓝奏云</button></div></section>
  }

  const treeNode = (nodePath, label, depth) => {
    const children = tree[nodePath] || []
    const open = Boolean(expanded[nodePath])
    return (
      <div key={nodePath} className="tree-node">
        <div className={`tree-row ${path === nodePath ? 'active' : ''}`} style={{ paddingLeft: 8 + depth * 14 }}>
          <button className="tree-toggle" aria-label={open ? '收起' : '展开'}
            onClick={(e) => { e.stopPropagation(); toggleTree(nodePath) }}>
            {children.length ? (open ? '▾' : '▸') : '·'}
          </button>
          <button className="tree-name" onClick={() => load(nodePath)} title={nodePath}>
            <Icon name="folder" size={13} />{label}
          </button>
        </div>
        {open && children.map((child) => treeNode(`${nodePath.replace(/\/$/, '')}/${child.name}`, child.name, depth + 1))}
      </div>
    )
  }

  return (
    <div className="cloud-shell">
      <aside className="card cloud-tree">
        <div className="card-head"><div><span className="eyebrow">TREE</span><h2>云端目录</h2></div>
          <button className="btn tiny ghost" onClick={() => { setTree({}); setExpanded({ '/': true }); load('/') }}>刷新</button></div>
        <div className="tree-body">
          <div className={`tree-row ${path === '/' ? 'active' : ''}`}>
            <span className="tree-toggle">▾</span>
            <button className="tree-name" onClick={() => load('/')}><Icon name="cloud" size={13} />根目录</button>
          </div>
          {(tree['/'] || []).map((f) => treeNode(`/${f.name}`, f.name, 1))}
        </div>
        {quota && <div className="quota-box">
          <div className="quota-head"><span>容量</span><span>{quota.used_text} / {quota.total_text}</span></div>
          <div className="quota-track"><i style={{ width: `${Math.min(100, quota.percent || 0)}%` }} /></div>
        </div>}
      </aside>

      <section className="card cloud-main">
        <div className="cloud-toolbar">
          <div className="crumb-row">
            <button className="crumb" onClick={() => load('/')}>根目录</button>
            {parts.map((part, i) => <span key={`${part}-${i}`} className="crumb-wrap">
              <Icon name="chevron" size={12} />
              <button className="crumb" onClick={() => load('/' + parts.slice(0, i + 1).join('/'))}>{part}</button>
            </span>)}
          </div>
          <div className="cloud-tools">
            <label className="cloud-search"><Icon name="search" size={13} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索当前目录" /></label>
            <button className="btn small ghost" disabled={loading} onClick={() => { load(path); loadQuota() }}>
              <Icon name="refresh" />刷新</button>
            <label className="switch-label" title="每 20 秒自动刷新">
              <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />自动刷新
            </label>
            {snap.role === 'developer' && <>
              <button className="btn small" onClick={mkdir}>新建文件夹</button>
              <button className="btn small primary" disabled={Boolean(busy)} onClick={upload}>
                <Icon name="upload" />上传</button>
            </>}
          </div>
        </div>
        <div className="cloud-meta">
          <span>{updatedAt ? `最后更新 ${updatedAt}` : '读取中…'}</span>
          <span>{filtered.folders.length} 个文件夹 · {filtered.files.length} 个文件{query ? '（已筛选）' : ''}</span>
          <button className="text-btn" onClick={() => copyShare(path)}>复制此目录分享链接</button>
        </div>
        {error && <p className="modal-error">{error}</p>}
        {loading && !data ? <p className="muted pad">正在读取云端目录…</p> : null}
        <div className="cloud-table" role="table" aria-label="云端文件">
          <div className="cloud-tr head" role="row">
            <span>名称</span><span>大小</span><span>修改时间</span><span>操作</span>
          </div>
          {filtered.folders.map((folder) => (
            <div key={`d${folder.id}`} className="cloud-tr" role="row">
              <button className="cloud-td-name" role="cell" onClick={() => load(full(folder.name))}>
                <span className="cloud-ico folder"><Icon name="folder" size={14} /></span>
                <span className="cloud-name">{folder.name}</span></button>
              <span role="cell" className="muted">—</span>
              <span role="cell" className="muted">{folder.time || '—'}</span>
              <span role="cell" className="cloud-actions">
                <button className="text-btn" onClick={() => copyShare(full(folder.name))}>分享</button>
                {snap.role === 'developer' && <button className="text-btn danger-text"
                  onClick={() => actions.cloudDelete('folder', folder.id, folder.name, full(folder.name))}>删除</button>}
              </span>
            </div>
          ))}
          {filtered.files.map((file) => (
            <div key={`f${file.id}`} className="cloud-tr" role="row">
              <button className="cloud-td-name" role="cell" onClick={() => setPeek(file)}>
                <span className="cloud-ico file"><Icon name="download" size={13} /></span>
                <span className="cloud-name" title={file.name}>{file.name}</span></button>
              <span role="cell" className="muted">{file.size || '—'}</span>
              <span role="cell" className="muted">{file.time || '—'}</span>
              <span role="cell" className="cloud-actions">
                {snap.role === 'developer' && <button className="text-btn danger-text"
                  onClick={() => actions.cloudDelete('file', file.id, file.name)}>删除</button>}
                {snap.role !== 'developer' && <span className="muted">只读</span>}
              </span>
            </div>
          ))}
          {!filtered.folders.length && !filtered.files.length &&
            <p className="muted pad">{query ? '没有匹配的文件。' : '这个目录是空的。'}</p>}
        </div>
        {peek && <div className="cloud-peek" role="dialog" aria-label="文件详情">
          <div className="cloud-peek-head"><strong>{peek.name}</strong>
            <button className="icon-btn" aria-label="关闭" onClick={() => setPeek(null)}>×</button></div>
          <div className="cloud-peek-grid">
            <div><span>大小</span><strong>{peek.size || '—'}</strong></div>
            <div><span>修改时间</span><strong>{peek.time || '—'}</strong></div>
            <div><span>下载次数</span><strong>{peek.downs ?? '—'}</strong></div>
            <div><span>文件 ID</span><strong>#{peek.id}</strong></div>
          </div>
          <div className="button-row">
            <button className="btn small ghost" onClick={async () => {
              try { await navigator.clipboard.writeText(peek.name); actions.toast('文件名已复制', 'success') }
              catch { actions.toast('复制失败', 'warning') }
            }}>复制文件名</button>
          </div>
        </div>}
        <p className="field-note">和网页版一样，这里显示的是账号里的真实目录；上传/删除会立即影响分享内容。</p>
      </section>
    </div>
  )
}
