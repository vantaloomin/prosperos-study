import { Check, GitBranch, RotateCcw, Square } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { UsageSummary } from '../../components/UsageSummary'
import { useAction } from '../../hooks/useAction'
import { isWorking } from './types'
import type { Candidate, Generation } from './types'
import { AttemptHistory } from './AttemptHistory'
import { RequestStatus } from './RequestStatus'
import { useRecovery } from './useRecovery'
import { recoverRequest, type SavedRequest } from './requestRecovery'
import { CleanupReview } from '../phrases/CleanupReview'
import { draftWording } from '../phrases/cleanupTypes'
import { TimingDetails } from './TimingDetails'
import { RecallReceipt } from './RecallReceipt'
import { ContinuityRevision } from './ContinuityRevision'
import { CandidateDraftEdits } from '../textEdits/CandidateDraftEdits'

export function CandidateView({ candidate, generation, onBranch, onClose, onAlternate }: { candidate: Candidate; generation: Generation; onBranch: (id: string) => void; onClose: () => void; onAlternate: (id: string) => void }) {
  const action = useAction()
  const cache = useQueryClient()
  const recovery = useRecovery<SavedRequest>(`roleplay:alternate:${candidate.id}`)
  const accept = (asNewBranch: boolean) => action.run(async () => {
    const result = await api<{ branch_id: string }>(`/candidates/${candidate.id}/accept`, { operation_id: operationId(), as_new_branch: asNewBranch, branch_name: `${candidate.profile.name} · another telling`, expected_wording_version: candidate.wording_version })
    onBranch(result.branch_id)
    onClose()
  })
  const control = (kind: 'cancel' | 'retry') => action.run(async () => { await api(`/candidates/${candidate.id}/${kind}`, kind === 'retry'
    ? { operation_id: `retry-${candidate.id}-${candidate.attempt}`, expected_attempt: candidate.attempt } : {}) })
  const alternate = () => action.run(async () => {
    const request: SavedRequest = recovery.latest() ?? { kind: 'alternate', path: `/candidates/${candidate.id}/alternatives`, body: { operation_id: operationId() } }
    recovery.store(request)
    const result = await recoverRequest<{ candidate_id: string }>(request, api)
    onAlternate(result.candidate_id)
    recovery.store(null)
  })
  return <section className="candidate-view"><RequestStatus candidate={candidate} /><CandidateText candidate={candidate} />
    <CandidateDraftEdits candidate={candidate} generation={generation} onBranch={onBranch} />
    <CleanupReview candidate={candidate} />
    <ContinuityRevision key={candidate.id} candidate={candidate} onAlternate={onAlternate} />
    <TimingDetails usage={candidate.usage} />
    <RecallReceipt receipt={candidate.usage.writer_recall} />
    <ErrorNotice message={recovery.problem || candidate.error || action.error} />
    {action.error && <button className="button" onClick={() => { action.clearError(); void cache.invalidateQueries({ queryKey: ['generation', generation.id] }) }}>Refresh draft wording</button>}
    <UsageSummary usage={candidate.usage} />
    <CandidateActions candidate={candidate} stale={generation.stale} busy={action.busy} onAccept={accept} onControl={control} />
    {candidate.status === 'done' && <div className="alternate-action"><button className="text-button" onClick={alternate} disabled={action.busy}><RotateCcw size={14} />Try another</button><p className="subtle">{candidate.usage.continuity_revision ? 'Another continuity proposal with the same saved concern and evidence. Your original remains available.' : "A new draft with this profile's saved settings, prompt, context and rolls. Enabled cleanup may add one polishing call. Existing text and continuations remain available."}</p></div>}
    <details className="request-details"><summary>Request details</summary><p>Saved request limit: {candidate.profile.config.timeout_seconds} seconds.</p>{candidate.activity?.error_kind && <p>Result: {candidate.activity.error_kind.replaceAll('_', ' ')}</p>}<AttemptHistory candidateId={candidate.id} attempt={candidate.attempt} /></details>
  </section>
}

function CandidateText({ candidate }: { candidate: Candidate }) {
  const empty = isWorking(candidate) ? "Waiting for the model's response…" : 'No draft text was returned. Your story is unchanged.'
  return <div className="prose candidate-prose">{draftWording(candidate.output, candidate.cleanup, candidate.text_edit) || <span className="subtle">{empty}</span>}</div>
}

function CandidateActions({ candidate, stale, busy, onAccept, onControl }: { candidate: Candidate; stale: boolean; busy: boolean; onAccept: (branch: boolean) => void; onControl: (kind: 'cancel' | 'retry') => void }) {
  if (isWorking(candidate)) return <div className="candidate-actions"><button className="button" onClick={() => onControl('cancel')} disabled={busy}><Square size={13} />{candidate.status === 'cleaning' ? 'Stop cleanup; keep original' : 'Stop generation'}</button><span className="subtle">You can close this view; the draft will keep running.</span></div>
  if (candidate.accepted_branch_id) return <div className="candidate-actions"><button className="button primary" onClick={() => onAccept(false)}><Check size={15} />Open accepted path</button></div>
  if (candidate.status !== 'done') return <div className="candidate-actions"><button className="button" onClick={() => onControl('retry')} disabled={busy}><RotateCcw size={15} />Retry original inputs</button><p className="subtle">Uses the original model settings, including the output limit. After changing a profile, close this draft and start a new continuation.</p></div>
  return <div className="candidate-actions">{!stale && <button className="button primary" disabled={busy} onClick={() => onAccept(false)}><Check size={15} />Keep</button>}<button className="button" disabled={busy} onClick={() => onAccept(true)}><GitBranch size={15} />Keep on new branch</button>{stale && <p className="subtle">The original story has moved on. A new branch preserves this draft's starting point.</p>}</div>
}
