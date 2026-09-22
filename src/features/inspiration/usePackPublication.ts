import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, ApiError, operationId } from '../../api'
import { useAction } from '../../hooks/useAction'
import { publishPersistent, usePersistent } from '../../hooks/usePersistent'
import type { PackChoice, PackReport, PackResult } from './types'

interface Request { operation_id: string; source_sha256: string; reviewed: boolean; choices: Omit<PackChoice, 'included'>[] }
interface Saved { state: 'pending' | 'complete'; request: Request }

export function usePackPublication(report: PackReport) {
  const key = `roleplay:pack-publication:${report.id}`
  const [saved, setSaved] = usePersistent<Saved | null>(key, null, true)
  const [local, setLocal] = useState<PackResult | null>(null)
  const action = useAction({ queryKey: ['inspiration'] })
  const receipt = useQuery({ queryKey: ['inspiration', 'pack-operation', saved?.request.operation_id], enabled: !!saved,
    queryFn: async () => {
      const value = await api<{ kind: string | null; result: PackResult | null }>(`/operations/${saved!.request.operation_id}`)
      if (value.kind && value.kind !== 'inspiration-pack-import') throw new Error('This receipt belongs to another action. Reopen the collection review.')
      return value
    } })
  const execute = (request: Request) => action.run(async () => {
    const pending: Saved = { state: 'pending', request }
    try { publishPersistent(key, pending) }
    catch { throw new Error('This browser could not save the pending import. Free browser storage before importing this collection.') }
    setSaved(pending)
    try {
      setLocal(await api<PackResult>(`/inspiration/packs/${report.id}/publish`, request))
      setSaved({ state: 'complete', request })
    } catch (error) {
      if (error instanceof ApiError && error.status < 500) setSaved(null)
      throw error
    }
  })
  const publish = (choices: PackChoice[], reviewed: boolean) => execute(saved?.request ?? {
    operation_id: operationId(), source_sha256: report.source_sha256, reviewed,
    choices: choices.filter(item => item.included).map(item => ({ key: item.key, duplicate_action: item.duplicate_action, target_deck_id: item.target_deck_id, expected_version_id: item.expected_version_id })) })
  const result = local ?? (saved ? receipt.data?.result : null)
  return { action, result, error: action.error || receipt.error?.message, pending: !!saved && !result,
    publish, retry: () => { if (saved) void execute(saved.request) }, reset: () => { setSaved(null); setLocal(null); action.clearError() } }
}
