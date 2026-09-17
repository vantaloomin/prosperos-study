import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api'
import { isWorking } from './types'
import type { Generation } from './types'

export function useGeneration(id: string) {
  const cache = useQueryClient()
  const query = useQuery({ queryKey: ['generation', id], queryFn: () => api<Generation>(`/generations/${id}`),
    refetchInterval: (current) => current.state.data?.candidates.some(isWorking) ? 1500 : false,
  })
  const active = query.data?.candidates.some(isWorking) ?? false
  useEffect(() => {
    if (!active) return
    const stream = new EventSource(`/api/generations/${id}/events`)
    stream.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data) as Pick<Generation, 'candidates' | 'stale'>
        cache.setQueryData<Generation>(['generation', id], (previous) => previous ? { ...previous, ...update } : previous)
      } catch {
        stream.close() // Polling remains available if a stream is interrupted or malformed.
      }
    }
    return () => stream.close()
  }, [id, active, cache])
  return query
}
