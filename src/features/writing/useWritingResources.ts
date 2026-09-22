import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import type { WritingPins, WritingResource } from './types'

export function useWritingResources() {
  return useQuery({ queryKey: ['writing-resources', true], queryFn: () => api<WritingResource[]>('/writing-resources?include_archived=true') })
}

export function useWritingVersion(id: string) {
  return useQuery({ queryKey: ['writing-version', id], queryFn: () => api<WritingResource>(`/writing-versions/${id}`), enabled: Boolean(id && id !== 'none' && id !== 'inherit') })
}

export function useWritingPins(storyId: string) {
  return useQuery({ queryKey: ['writing-pins', storyId], queryFn: () => api<WritingPins>(`/stories/${storyId}/writing-preferences`) })
}
