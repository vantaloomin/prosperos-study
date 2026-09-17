import { Component, type ReactNode } from 'react'
import { RotateCcw } from 'lucide-react'

export class RecoveryBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  render() {
    if (!this.state.failed) return this.props.children
    return <main className="page recovery-notice" role="alert"><span className="eyebrow">Your workspace</span><h1>This view couldn't load.</h1><p>Your saved stories remain on this device. Reload to reopen the workspace, including after an application update.</p><button className="button primary" onClick={() => window.location.reload()}><RotateCcw size={16} />Reload workspace</button></main>
  }
}
