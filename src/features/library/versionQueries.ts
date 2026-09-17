import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import type { AssetVersion, VersionReference } from '../../types'

export function useVersions(assetId: string) {
  return useQuery({ queryKey: ['versions', assetId], queryFn: () => api<AssetVersion[]>(`/library/${assetId}/versions`) })
}

export function useReferences(ids: string[]) {
  return useQuery({ queryKey: ['version-references', ids], queryFn: () => api<VersionReference[]>('/library/versions/lookup', { version_ids: ids }), enabled: ids.length > 0 })
}
