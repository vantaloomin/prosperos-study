import { useId, useState } from 'react'
import { api, ApiError, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { recoverRequest, type SavedRequest } from './requestRecovery'
import { useRecovery } from './useRecovery'
import type { Candidate } from './types'

export interface ContinuityRevisionData {
  version: number
  candidate_id: string
  concern: string
  prompt: string
  content: string
  estimated_input_tokens: number
}

export function ContinuityRevision({ candidate, onAlternate }: { candidate: Candidate; onAlternate: (id: string) => void }) {
  return <><RevisionReceipt revision={candidate.usage.continuity_revision} onAlternate={onAlternate} />
    {candidate.status === 'done' && !candidate.accepted_node_id && <RevisionForm candidate={candidate} onAlternate={onAlternate} />}
  </>
}

function RevisionForm({ candidate, onAlternate }: { candidate: Candidate; onAlternate: (id: string) => void }) {
  const [concern, setConcern] = useState('')
  const fieldId = useId()
  const action = useAction()
  const recovery = useRecovery<SavedRequest>(`roleplay:continuity-revision:${candidate.id}`)
  const submit = () => action.run(async () => {
    let saved = recovery.latest()
    if (!saved) {
      const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(candidate.text_edit?.text ?? candidate.output))
      saved = { kind: 'continuity_revision', path: `/candidates/${candidate.id}/continuity-revision`, body: {
        operation_id: operationId(), expected_attempt: candidate.attempt,
        original_sha256: Array.from(new Uint8Array(hash), value => value.toString(16).padStart(2, '0')).join(''), concern, expected_wording_version: candidate.wording_version,
      } }
      recovery.store(saved)
    }
    try {
      const result = await recoverRequest<{ candidate_id: string }>(saved, api)
      onAlternate(result.candidate_id)
      recovery.store(null)
      setConcern('')
    } catch (error) {
      if (error instanceof ApiError && [400, 409, 422].includes(error.status)) recovery.store(null)
      throw error
    }
  })
  return <details className="request-details">
      <summary>Revise continuity</summary>
      <p className="subtle">Describe a suspected mismatch with the saved story evidence. One model request proposes another telling; the original stays available. Missing history may remain unresolved.</p>
      <RevisionSource candidate={candidate} />
      <label className="field" htmlFor={fieldId}><span>Continuity concern</span>
      <textarea id={fieldId} value={recovery.pending ? String(recovery.pending.body.concern) : concern} onChange={event => setConcern(event.target.value)} rows={3} maxLength={1000} disabled={action.busy || !!recovery.pending} placeholder="For example: the recipient already signed for this parcel, but this draft has them still waiting." /></label>
      <div className="candidate-actions"><button className="button" disabled={action.busy || !!recovery.problem || (!recovery.pending && !concern.trim())} onClick={submit}>{buttonLabel(action.busy, !!recovery.pending)}</button></div>
      <ErrorNotice message={recovery.problem || action.error} />
    </details>
}

function RevisionSource({ candidate }: { candidate: Candidate }) {
  if (candidate.text_edit) return <p className="subtle">Revision starts from author revision {candidate.text_edit.revision}, using the original saved Story evidence. Later draft edits do not change that request.</p>
  return candidate.cleanup?.selected === 'cleaned' ? <p className="subtle">Revision starts from the original draft, before wording cleanup.</p> : null
}

function RevisionReceipt({ revision, onAlternate }: { revision?: ContinuityRevisionData; onAlternate: (id: string) => void }) {
  if (!revision) return null
  return <details className="request-details"><summary>Continuity revision - compare with original</summary>
    <p>{revision.concern}</p><p className="subtle">This is a proposed revision. Check its meaning and remaining uncertainties before keeping it.</p>
    <details><summary>Original wording used for this revision</summary><div className="prose">{JSON.parse(revision.content).draft as string}</div></details>
    <button className="text-button" onClick={() => onAlternate(revision.candidate_id)}>Show original draft</button>
    <details><summary>Exact revision request</summary><p>Estimated input: {revision.estimated_input_tokens.toLocaleString()} tokens.</p><pre>{revision.prompt}</pre><pre>{JSON.stringify(JSON.parse(revision.content), null, 2)}</pre></details>
  </details>
}

function buttonLabel(busy: boolean, pending: boolean) { return busy ? 'Requesting revision...' : pending ? 'Recover revision request' : 'Propose revision' }
