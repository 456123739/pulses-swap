import React from 'react'

const paths = {
  home: 'M3 10.5 12 3l9 7.5V21h-6v-6H9v6H3z',
  manage: 'M4 6h16M4 12h16M4 18h16',
  settings: 'M12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6Zm8.2 3.8c0 .5 0 1-.1 1.4l2 1.6-1.9 3.3-2.4-1a8 8 0 0 1-2.4 1.4l-.4 2.6h-3.8l-.4-2.6a8 8 0 0 1-2.4-1.4l-2.4 1L3.1 15l2-1.6A8 8 0 0 1 5 12c0-.5 0-1 .1-1.4l-2-1.6 1.9-3.3 2.4 1A8 8 0 0 1 9.8 5l.4-2.6h3.8l.4 2.6a8 8 0 0 1 2.4 1.4l2.4-1 1.9 3.3-2 1.6c.1.4.1.9.1 1.4Z',
  log: 'M5 4h14v16H5zM8 8h8M8 12h8M8 16h5',
  folder: 'M3 6h7l2 2h9v11H3z',
  plus: 'M12 5v14M5 12h14',
  refresh: 'M20 11a8 8 0 1 1-2.3-5.7M20 4v7h-7',
  chevron: 'm9 5 7 7-7 7',
  close: 'm6 6 12 12M18 6 6 18',
  check: 'm5 12 4 4L19 6',
  cloud: 'M7 18h10a4 4 0 0 0 .8-7.9A6 6 0 0 0 6.1 9 4.5 4.5 0 0 0 7 18Z',
  upload: 'M12 16V4m0 0L7 9m5-5 5 5M5 20h14',
  download: 'M12 4v12m0 0 5-5m-5 5-5-5M5 20h14',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-8 8a8 8 0 0 1 16 0',
}

export default function Icon({ name, size = 18, className = '' }) {
  const d = paths[name] || paths.home
  return (
    <svg className={className} width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="1.6"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}
