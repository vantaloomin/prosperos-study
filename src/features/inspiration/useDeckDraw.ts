import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, ApiError, operationId } from '../../api'
import { useAction } from '../../hooks/useAction'
import { publishPersistent, usePersistent } from '../../hooks/usePersistent'
import type { Branch } from '../../types'
import type { Deck, DeckDraw, DeckFilters } from './types'

interface DrawRequest { operation_id: string; filters: DeckFilters; branch_id?: string; expected_revision?: number }

export function useDeckDraw(deck: Deck, branch?: Branch) {
  const key = `roleplay:deck-draw:${deck.id}:${branch?.id ?? 'library'}`
  const [pending, setPending] = usePersistent<DrawRequest | null>(key, null, true)
  const [selected, setSelected] = usePersistent<string | null>(`${key}:selected`, null)
  const action = useAction({ queryKey: ['inspiration'] })
  const [offset, setOffset] = useState(0)
  const history = useQuery({ queryKey: ['inspiration', 'draws', deck.id, branch?.id, offset], queryFn: () => api<DeckDraw[]>(`/inspiration/draws?version_id=${deck.id}&offset=${offset}${branch ? `&branch_id=${branch.id}` : ''}`) })
  const receipt = useQuery({ queryKey: ['inspiration', 'draw', selected], queryFn: () => api<DeckDraw>(`/inspiration/draws/${selected}`), enabled: !!selected })
  const execute = (request: DrawRequest) => action.run(async () => {
    // A response can be lost after commit. Persist the retry identity before
    // sending; refuse the draw if this browser cannot retain its pending request.
    try { publishPersistent(key, request) }
    catch { throw new Error('This browser could not save the pending draw. Free browser storage before recording a draw.') }
    setPending(request)
    try {
      const result = await api<DeckDraw>(`/inspiration/versions/${deck.id}/draws`, request)
      setSelected(result.id); setPending(null); setOffset(0)
    } catch (error) {
      if (error instanceof ApiError && error.status < 500) setPending(null)
      throw error
    }
  })
  const draw = (filters: DeckFilters) => execute(pending ?? { operation_id: operationId(), filters, ...(branch ? { branch_id: branch.id, expected_revision: branch.revision } : {}) })
  return { action, pending, history, receipt, selected, setSelected, offset, setOffset, draw, retry: () => { if (pending) void execute(pending) } }
}
