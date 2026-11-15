import React, { useState } from 'react'

/** 极简说明：悬浮 / 聚焦 / 点一下显示一句话；气泡只在打开时挂载，不污染按钮文字。 */
export default function Hint({ text, edge = 'top', label = '说明' }) {
  const [open, setOpen] = useState(false)
  return (
    <span
      className="hint" data-edge={edge} tabIndex={0} role="button"
      aria-label={`${label}：${text}`} aria-expanded={open}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
      onClick={(e) => { e.stopPropagation(); setOpen((v) => !v) }}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setOpen((v) => !v) } }}
    >
      <span className="hint-mark" aria-hidden="true" />
      {open && <span className="hint-bubble" role="tooltip">{text}</span>}
    </span>
  )
}
