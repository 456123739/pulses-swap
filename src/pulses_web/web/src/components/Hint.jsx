import React, { useRef, useState } from 'react'
import { createPortal } from 'react-dom'

/**
 * 极简说明：悬浮 / 聚焦 / 点一下显示一句话。
 * 气泡用 portal 挂到 body 上，避免被列表/卡片的 overflow 裁掉。
 */
export default function Hint({ text, edge = 'top', label = '说明' }) {
  const [open, setOpen] = useState(false)
  const [pos, setPos] = useState(null)
  const markRef = useRef(null)

  const place = () => {
    const box = markRef.current?.getBoundingClientRect()
    if (!box) return
    const width = Math.min(300, window.innerWidth - 24)
    const left = Math.max(12 + width / 2, Math.min(window.innerWidth - 12 - width / 2, box.left + box.width / 2))
    const flip = box.top < 110
    setPos({ left, top: flip ? box.bottom + 8 : box.top - 8, flip, width })
  }
  const show = () => { place(); setOpen(true) }
  const hide = () => setOpen(false)
  const toggle = (e) => {
    e.stopPropagation()
    if (open) hide()
    else show()
  }
  return (
    <span
      ref={markRef}
      className="hint" data-edge={edge} tabIndex={0} role="button"
      aria-label={`${label}：${text}`} aria-expanded={open}
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      onClick={toggle}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(e) } }}
    >
      <span className="hint-mark" aria-hidden="true" />
      {open && pos && createPortal(
        <span className="hint-bubble hint-bubble-portal" role="tooltip"
          style={{ left: pos.left, top: pos.top, width: pos.width,
            transform: pos.flip ? 'translate(-50%, 0)' : 'translate(-50%, -100%)' }}>
          {text}
        </span>, document.body)}
    </span>
  )
}
