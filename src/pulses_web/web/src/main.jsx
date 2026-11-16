import '@fontsource-variable/inter'
import '@fontsource-variable/manrope'
import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './styles.css'

/** 渲染崩了也要给用户一个出口，而不是整片白屏。 */
class Boundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('UI crashed', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="crash-screen" role="alert">
        <h1>界面出了点问题</h1>
        <p>你的预设和游戏文件没有被动过。可以重载界面继续，或者到日志页看看原因。</p>
        <pre>{String(this.state.error?.message || this.state.error)}</pre>
        <div className="button-row">
          <button className="btn primary" onClick={() => window.location.reload()}>重载界面</button>
          <button className="btn ghost" onClick={() => { this.setState({ error: null }) }}>再试一次</button>
        </div>
      </div>
    )
  }
}

createRoot(document.getElementById('root')).render(
  <Boundary>
    <App />
  </Boundary>,
)
