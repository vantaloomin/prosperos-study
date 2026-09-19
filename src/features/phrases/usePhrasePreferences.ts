import { useCallback, useEffect, useRef, useState } from 'react'
import { emptyPreferences, parsePreferences, preferenceKey, savePreferences } from './preferences'
import type { PhrasePreferences } from './types'

function load(key: string) {
  try {
    const raw = localStorage.getItem(key)
    return { raw, value: parsePreferences(raw), error: '', unreadable: false }
  } catch {
    return { raw: null, value: emptyPreferences(), error: 'Phrase-check choices could not be read on this device. Reset the local choices to continue.', unreadable: true }
  }
}

export function usePhrasePreferences(branchId: string) {
  const key = preferenceKey(branchId)
  const [state, setState] = useState(() => load(key))
  const latest = useRef(state)
  const publish = useCallback((next: typeof state) => { latest.current = next; setState(next) }, [])
  useEffect(() => {
    const sync = (event: StorageEvent) => { if (event.key === key || event.key === null) publish(load(key)) }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [key, publish])
  const update = (change: (value: PhrasePreferences) => PhrasePreferences) => {
    let value = latest.current.value
    try {
      if (latest.current.unreadable) throw new Error(latest.current.error)
      value = change(value)
      const raw = savePreferences(localStorage, key, latest.current.raw, value)
      publish({ raw, value, error: '', unreadable: false })
    } catch (failure) {
      const reason = failure instanceof Error ? failure.message : 'Storage unavailable.'
      publish({ ...latest.current, value, error: `This choice has not been saved on this device. ${reason}` })
    }
  }
  const reset = () => {
    try {
      localStorage.removeItem(key)
      publish({ raw: null, value: emptyPreferences(), error: '', unreadable: false })
    } catch { publish({ ...latest.current, error: 'The local phrase-check choices could not be reset.' }) }
  }
  return { ...state, update, reset, reload: () => publish(load(key)) }
}
