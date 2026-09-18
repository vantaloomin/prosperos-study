import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api'

interface Preparation { opportunity_id: string | null; stopped: number; stale: boolean; error: string; jobs: { status: string }[] }
const active = (run?: Preparation) => !run || (!run.stopped && !run.stale && !run.error && !run.opportunity_id && run.jobs.every(job => ['running', 'queued', 'done'].includes(job.status)))

export function PreparedBeatStatus({ id, branchId, onOpen }: { id: string; branchId: string; onOpen: () => void }) {
  const cache = useQueryClient()
  const query = useQuery({ queryKey: ['assessment', id], queryFn: () => api<Preparation>(`/assessments/${id}`), refetchInterval: current => active(current.state.data) ? 1500 : false })
  const marker = query.data ? `${query.data.opportunity_id}:${query.data.stopped}:${query.data.stale}` : ''
  useEffect(() => { if (marker) void cache.invalidateQueries({ queryKey: ['branch', branchId] }) }, [marker, cache, branchId])
  return <div className="prepared-choice"><p role="status" className="subtle">{query.error ? 'Beat preparation status is unavailable. Writing is still available.' : preparationLabel(query.data)}</p><button className="text-button" onClick={onOpen}>Inspect beat preparation</button></div>
}

function preparationLabel(run?: Preparation) {
  if (!run || active(run)) return 'Scribe is checking the accepted beat. Writing can continue immediately.'
  if (run.stopped || run.stale) return 'This preparation was skipped or its inputs changed. Writing continues without it.'
  if (run.opportunity_id) return 'The next beat is prepared for this point in the Story.'
  return 'Beat preparation needs attention. Writing can continue without it; open the report to retry.'
}
