import { useCallback, useEffect, useState } from 'react'
import { readRecovery, writeRecovery } from './requestRecovery'

function read<T>(key: string) {
  try { return { value: readRecovery<T>(key), error: '' } }
  catch { return { value: null, error: 'The saved recovery record cannot be read. No new request will be sent. Check browser storage and the saved request before trying again.' } }
}

export function useRecovery<T>(key: string) {
  const [state, setState] = useState(() => read<T>(key))
  useEffect(() => {
    const sync = (event: StorageEvent) => { if (event.key === key) setState(read<T>(key)) }
    window.addEventListener('storage', sync)
    return () => window.removeEventListener('storage', sync)
  }, [key])
  const store = useCallback((value: T | null) => {
    writeRecovery(key, value)
    setState({ value, error: '' })
  }, [key])
  const latest = () => { const current = read<T>(key); if (current.error) throw new Error(current.error); return current.value }
  return { pending: state.value, problem: state.error, store, latest }
}
