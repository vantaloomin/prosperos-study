import { useRef, useState } from 'react'
import { useQueryClient, type QueryFilters } from '@tanstack/react-query'

export function useAction(refresh?: QueryFilters) {
  const cache = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inFlight = useRef(false)
  async function run(action: () => Promise<void>) {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError('')
    try {
      await action()
      await cache.invalidateQueries(refresh)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Something went wrong. Please try again.')
    } finally { inFlight.current = false; setBusy(false) }
  }
  return { run, busy, error, clearError: () => setError('') }
}
