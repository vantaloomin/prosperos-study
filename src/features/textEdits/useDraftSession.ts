import { useEffect, useSyncExternalStore } from 'react'
import type { DraftController, DraftSnapshot, DraftState } from './draftState'

export type DraftSession<T, S extends DraftSnapshot> = DraftState<T, S> & { controller: DraftController<T, S>; target: T }

export function useDraftSession<T, S extends DraftSnapshot>(controller: DraftController<T, S>): DraftSession<T, S> {
  const state = useSyncExternalStore(controller.subscribe, controller.getState)
  useEffect(() => {
    const refresh = () => { void controller.refresh() }
    void controller.refresh().then(controller.importLegacy)
    const timer = window.setInterval(refresh, 2500)
    window.addEventListener('focus', refresh)
    return () => {
      window.clearInterval(timer); window.removeEventListener('focus', refresh)
      const current = controller.getState()
      if (current.dirty && current.phase === 'ready') void controller.flush().catch(() => {})
    }
  }, [controller])
  useEffect(() => {
    if (!state.dirty || state.phase !== 'ready' || state.error) return
    const timer = window.setTimeout(() => { void controller.flush().catch(() => {}) }, 500)
    return () => window.clearTimeout(timer)
  }, [controller, state.text, state.dirty, state.phase, state.error])
  return { ...state, controller, target: controller.target }
}
