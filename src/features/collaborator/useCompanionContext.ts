import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import type { ContextHead, ContextSource } from './contextTypes'
import { followCompanionFocus, pinCompanionFocus } from './companionFocus'

export function useCompanionContext(threadId: string) {
  const cache = useQueryClient()
  const query = useQuery({ queryKey: ['side-context', threadId], queryFn: () => api<ContextHead>(`/side-conversations/${threadId}/context`), refetchInterval: 2500 })
  const pin = async (source: ContextSource) => {
    if (!query.data) throw new Error('Wait for the saved Companion target before changing it.')
    const result = await api<ContextHead>(`/side-conversations/${threadId}/context`, { operation_id: operationId(), expected_revision: query.data.revision, source })
    cache.setQueryData(['side-context', threadId], result)
    pinCompanionFocus({ storyId: result.context!.story_id, branchId: result.context!.branch.id }, threadId)
  }
  const follow = async () => {
    if (!query.data) throw new Error('Wait for the saved Companion target before changing it.')
    const result = await api<ContextHead>(`/side-conversations/${threadId}/context/follow`, { operation_id: operationId(), expected_revision: query.data.revision })
    cache.setQueryData(['side-context', threadId], result)
    followCompanionFocus()
  }
  return { ...query, pin, follow }
}
