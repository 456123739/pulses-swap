import React, { useCallback, useEffect, useState } from 'react'
import Icon from './Icons.jsx'
import Hint from './Hint.jsx'
import { invoke, pickFiles } from '../bridge.js'

/** 云端文件：浏览 / 新建文件夹 / 上传。开发者发更新包、清理测试文件都在这。 */
export default function CloudFiles({ snap, actions, busy }) {
  const [path, setPath] = useState('/')
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [quota, setQuota] = useState(null)
  const accountOk = Boolean(snap.online.account?.label) && snap.online.available !== false

  const load = useCallback(async (target) => {
    if (!accountOk) return
    setLoading(true); setError('')
    try {
      const out = await invoke('online.cloud.browse', { path: target })
      setData(out); setPath(out?.path || target)
    } catch (err) {
      setData(null); setError(err.message)
    } finally { setLoading(false) }
  }, [accountOk])

  useEffect(() => { load('/') }, [load])
  useEffect(() => { if (data && snap.revision) load(data.path || path) },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [snap.revision])
  useEffect(() => {
    if (!accountOk) return
    invoke('online.cloud.quota').then((out) => setQuota(out?.quota || null)).catch(() => {})
  }, [accountOk])

  const parts = path.split('/').filter(Boolean)
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
    return (
      <section className="card cloud-panel">
        <div className="empty"><div className="empty-orbit" /><h3>先登录蓝奏云</h3>
          <p>云端文件需要账号；登录后可以浏览、新建文件夹和上传。</p>
          <button className="btn primary" onClick={actions.login}>登录蓝奏云</button></div>
      </section>
    )
  }

  return (
    <section className="card cloud-panel">
      <div className="card-head">
        <div><span className="eyebrow">CLOUD</span><h2>云端文件</h2></div>
        <div className="button-row">
          <button className="btn small ghost" disabled={loading} onClick={() => load(path)}>刷新</button>
          {snap.role === 'developer' && <>
            <button className="btn small" onClick={mkdir}>新建文件夹</button>
            <button className="btn small primary" disabled={Boolean(busy)} onClick={upload}>
              <Icon name="upload" />上传文件
              <Hint text="选本地文件或文件夹，会上传到当前云端目录；同名文件会被覆盖。" />
            </button>
          </>}
        </div>
      </div>
      <div className="cloud-path">
        <button className="crumb" onClick={() => load('/')}>云端根目录</button>
        {parts.map((part, i) => (
          <span key={`${part}-${i}`} className="crumb-wrap">
            <Icon name="chevron" size={12} />
            <button className="crumb" onClick={() => load('/' + parts.slice(0, i + 1).join('/'))}>{part}</button>
          </span>
        ))}
        {quota && (quota.used_text || quota.total_text) &&
          <span className="crumb-quota">{[quota.used_text, quota.total_text].filter(Boolean).join(' / ')}</span>}
      </div>
      {error && <p className="modal-error">{error}</p>}
      {loading && !data ? <p className="muted pad">正在读取云端目录…</p> : null}
      {data ? <>
        <div className="cloud-list">
          {data.folders.map((folder) => (
            <div key={`d${folder.id}`} className="cloud-row folder-wrap">
              <button className="cloud-row-main" onClick={() => load(`${path.replace(/\/$/, '')}/${folder.name}`)}>
                <span className="cloud-ico"><Icon name="folder" size={15} /></span>
                <span className="cloud-name">{folder.name}</span>
                <Icon name="chevron" size={13} />
              </button>
              {snap.role === 'developer' && <button className="cloud-del" title="删除文件夹"
                onClick={() => actions.cloudDelete('folder', folder.id, folder.name)}>删除</button>}
            </div>
          ))}
          {data.files.map((file) => (
            <div key={`f${file.id}`} className="cloud-row">
              <span className="cloud-ico file"><Icon name="download" size={14} /></span>
              <span className="cloud-name" title={file.name}>{file.name}</span>
              <span className="muted">{file.size || ''}</span>
              {snap.role === 'developer' && <button className="cloud-del" title="删除文件"
                onClick={() => actions.cloudDelete('file', file.id, file.name)}>删除</button>}
            </div>
          ))}
          {!data.folders.length && !data.files.length &&
            <p className="muted pad">这个目录是空的。上传更新包后，把分享链接发给玩家即可。</p>}
        </div>
        <p className="field-note">玩家看到的是分享链接里的内容；这里的测试文件建议先删掉再分享。</p>
      </> : null}
    </section>
  )
}
