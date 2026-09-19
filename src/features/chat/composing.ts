import { api } from '../../api'

let lastNotice = 0

export function noteComposing() {
  const now = Date.now()
  if (now - lastNotice < 1000) return
  lastNotice = now
  // A scheduling hint contains no draft text and never blocks editing or sending.
  void api('/reading-time/composing', {}).catch(() => undefined)
}
