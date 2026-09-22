import { useState, useCallback, useEffect } from 'react'

export function publishPersistent<T>(key: string, value: T) {
  localStorage.setItem(key, JSON.stringify(value))
  window.dispatchEvent(new CustomEvent('roleplay:persistent-change', { detail: { key, value } }))
}

function read<T>(key: string, fallback: T): T {
  try {
    const stored = localStorage.getItem(key)
    return stored === null ? fallback : JSON.parse(stored) as T
  } catch { return fallback }
}

export function usePersistent<T>(key: string, fallback: T, synchronize = false) {
  const [value, setValue] = useState<T>(() => read(key, fallback))
  const update = useCallback((next: T) => {
    setValue(next)
    try { publishPersistent(key, next) } catch { /* Database saves stay independent. */ }
  }, [key])
  useEffect(() => {
    if (!synchronize) return
    const sync = (event: StorageEvent) => { if (event.key === key && event.newValue !== null) { try { setValue(JSON.parse(event.newValue) as T) } catch { /* Keep the last valid value. */ } } }
    const local = (event: Event) => { const detail = (event as CustomEvent<{ key: string; value: T }>).detail; if (detail.key === key) setValue(detail.value) }
    window.addEventListener('storage', sync)
    window.addEventListener('roleplay:persistent-change', local)
    return () => { window.removeEventListener('storage', sync); window.removeEventListener('roleplay:persistent-change', local) }
  }, [key, synchronize])
  return [value, update] as const
}
