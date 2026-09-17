import { Check, GitBranch, RotateCcw, Square } from 'lucide-react'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { isWorking } from './types'
import type { Candidate, Generation } from './types'
import { AttemptHistory } from './AttemptHistory'

export function CandidateView({ candidate, generation, onBranch, onClose, onAlternate }: { candidate: Candidate; generation: Generation; onBranch: (id: string) => void; onClose: () => void; onAlternate: (id: string) => void }) {
  const action = useAction()
  const accept = (asNewBranch: boolean) => action.run(async () => {
    const result = await api<{ branch_id: string }>(`/candidates/${candidate.id}/accept`, { operation_id: operationId(), as_new_branch: asNewBranch, branch_name: `${candidate.profile.name} · another telling` })
    onBranch(result.branch_id)
    onClose()
  })
  const control = (kind: 'cancel' | 'retry') => action.run(async () => { await api(`/candidates/${candidate.id}/${kind}`, {}) })
  const alternate = () => action.run(async () => {
    const result = await api<{ candidate_id: string }>(`/candidates/${candidate.id}/alternatives`, { operation_id: operationId() })
    onAlternate(result.candidate_id)
  })
  return <section className="candidate-view"><div className="candidate-meta"><span>{candidate.profile.config.model}</span><span role="status">{candidate.status} · attempt {candidate.attempt}</span></div><CandidateText candidate={candidate} />
    <ErrorNotice message={candidate.error || action.error} />
    <CandidateActions candidate={candidate} stale={generation.stale} busy={action.busy} onAccept={accept} onControl={control} />
    {candidate.status === 'done' && <div className="alternate-action"><button className="text-button" onClick={alternate} disabled={action.busy}><RotateCcw size={14} />Generate another telling</button><p className="subtle">One request with this profile's saved settings, prompt, context and rolls. Existing text and continuations remain available.</p></div>}
    <Usage usage={candidate.usage} />
    <AttemptHistory candidateId={candidate.id} attempt={candidate.attempt} />
  </section>
}

function CandidateText({ candidate }: { candidate: Candidate }) {
  const empty = isWorking(candidate) ? "Waiting for the model's response…" : 'No draft text was returned. Your story is unchanged.'
  return <div className="prose candidate-prose">{candidate.output || <span className="subtle">{empty}</span>}</div>
}

function CandidateActions({ candidate, stale, busy, onAccept, onControl }: { candidate: Candidate; stale: boolean; busy: boolean; onAccept: (branch: boolean) => void; onControl: (kind: 'cancel' | 'retry') => void }) {
  if (isWorking(candidate)) return <div className="candidate-actions"><button className="button" onClick={() => onControl('cancel')} disabled={busy}><Square size={13} />Stop generation</button><span className="subtle">You can close this view; the draft will keep running.</span></div>
  if (candidate.accepted_branch_id) return <div className="candidate-actions"><button className="button primary" onClick={() => onAccept(false)}><Check size={15} />Open accepted path</button></div>
  if (candidate.status !== 'done') return <div className="candidate-actions"><button className="button" onClick={() => onControl('retry')} disabled={busy}><RotateCcw size={15} />Retry original inputs</button><p className="subtle">Uses the original model settings, including the output limit. After changing a profile, close this draft and start a new continuation.</p></div>
  return <div className="candidate-actions">{!stale && <button className="button primary" disabled={busy} onClick={() => onAccept(false)}><Check size={15} />Accept & continue</button>}<button className="button" disabled={busy} onClick={() => onAccept(true)}><GitBranch size={15} />Keep as a new branch</button>{stale && <p className="subtle">The original story has moved on. A new branch preserves this draft's starting point.</p>}</div>
}

function Usage({ usage }: { usage: Record<string, unknown> }) {
  const entries = Object.entries(usage)
  if (!entries.length) return <p className="usage-note">Token usage has not been reported by this provider.</p>
  return <details className="usage-details"><summary>Reported usage</summary><pre>{JSON.stringify(usage, null, 2)}</pre></details>
}
