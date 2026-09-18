import { useState, useCallback, useEffect } from 'react'

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
    try { localStorage.setItem(key, JSON.stringify(next)) } catch { /* Database saves stay independent. */ }
  }, [key])
  useEffect(() => {
    if (!synchronize) return
    const sync = (event: StorageEvent) => { if (event.key === key && event.newValue !== null) { try { setValue(JSON.parse(event.newValue) as T) } catch { /* Keep the last valid value. */ } } }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [key, synchronize])
  return [value, update] as const
}
