import type { Selection } from '../../types'

let opened: Window | null = null
export const isCompanionWindow = () => new URLSearchParams(window.location.search).get('companion') === '1'

export function openCompanionWindow(selection: Selection) {
  if (opened && !opened.closed) { opened.focus(); return opened }
  const url = new URL(window.location.href)
  url.search = new URLSearchParams({ companion: '1', story: selection.storyId, branch: selection.branchId }).toString()
  url.hash = ''
  opened = window.open(url, 'prospero-companion', 'popup=yes,width=680,height=850,resizable=yes,scrollbars=yes')
  if (!opened) throw new Error('The browser blocked Pop Out. Allow pop-ups for this app, then choose Pop Out again. Your conversation stays here.')
  opened.focus()
  return opened
}

export async function returnToWorkspace(selection: Selection) {
  localStorage.setItem('roleplay:selection', JSON.stringify(selection))
  try {
    if (window.opener && !window.opener.closed && window.opener.location.origin === window.location.origin) {
      if (await returnAcknowledged(window.opener, selection)) { window.opener.focus(); window.close(); return }
    }
  } catch { /* A closed or navigated parent does not prevent independent use. */ }
  window.location.assign(new URL('/?companion_return=1', window.location.origin))
}

export function returnSelection(event: MessageEvent): Selection | null {
  if (event.origin !== window.location.origin || event.data?.type !== 'prospero:companion-return') return null
  try { if (!event.source || (event.source as Window).opener !== window) return null } catch { return null }
  const value = event.data.selection as Selection | undefined
  if (!value || !validId(value.storyId) || !validId(value.branchId)) return null
  return { storyId: value.storyId, branchId: value.branchId }
}

const validId = (value: unknown) => typeof value === 'string' && value.length > 0 && value.length <= 100

export function acknowledgeReturn(event: MessageEvent) {
  if (typeof event.data.nonce === 'string') (event.source as Window).postMessage({ type: 'prospero:companion-returned', nonce: event.data.nonce }, event.origin)
}

function returnAcknowledged(parent: Window, selection: Selection): Promise<boolean> {
  return new Promise(resolve => {
    const nonce = crypto.randomUUID()
    const finish = (received: boolean) => { clearTimeout(timer); window.removeEventListener('message', receive); resolve(received) }
    const receive = (event: MessageEvent) => {
      if (event.origin === window.location.origin && event.source === parent && event.data?.type === 'prospero:companion-returned' && event.data.nonce === nonce) finish(true)
    }
    const timer = setTimeout(() => finish(false), 2000)
    window.addEventListener('message', receive)
    parent.postMessage({ type: 'prospero:companion-return', selection, nonce }, window.location.origin)
  })
}
