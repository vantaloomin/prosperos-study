import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api'
import { sceneWorking, type SceneRun } from './types'

export function useScene(id: string) {
  const cache = useQueryClient()
  const query = useQuery({ queryKey: ['scene', id], queryFn: () => api<SceneRun>(`/scenes/${id}`), refetchInterval: (current) => current.state.data?.jobs.some(sceneWorking) ? 1500 : false })
  const active = query.data?.jobs.some(sceneWorking) ?? false
  useEffect(() => {
    if (!active) return
    const stream = new EventSource(`/api/scenes/${id}/events`)
    stream.onmessage = (event) => { try { cache.setQueryData(['scene', id], JSON.parse(event.data)) } catch { stream.close() } }
    return () => stream.close()
  }, [active, id, cache])
  return query
}
