import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Candidate } from '../generation/types'
import { originalWords, type Cleanup } from './cleanupTypes'
import './cleanup.css'

export function CleanupReview({ candidate }: { candidate: Candidate }) {
  const action = useAction()
  const cleanup = candidate.cleanup
  if (!cleanup) return null
  const choose = (selected: Cleanup['selected']) => action.run(async () => {
    await api(`/candidates/${candidate.id}/cleanup-selection`, {
      operation_id: operationId(), expected_attempt: candidate.attempt,
      original_sha256: cleanup.snapshot.original_sha256, selected,
    })
  })
  return <section className="cleanup-review" aria-label="Draft wording cleanup">
    <p role="status">{cleanupMessage(cleanup, !!candidate.text_edit)}</p>
    <CleanupStop candidate={candidate} busy={action.busy} stop={() => void action.run(async () => { await api(`/candidates/${candidate.id}/cancel`, {}) })} />
    {cleanup.status === 'done' && <>
      <p className="subtle">{changeLabel(cleanup.edits.length)} Check that the meaning and voice still fit before keeping this draft.</p>
      <CleanupComparison cleanup={cleanup} />
      {canChooseCleanup(candidate) && <div className="candidate-actions">
        <button className="button" aria-pressed={cleanup.selected === 'original'} disabled={action.busy || candidate.status !== 'done'} onClick={() => void choose('original')}>Use original wording</button>
        <button className="button" aria-pressed={cleanup.selected === 'cleaned' && !cleanup.stale} disabled={action.busy || cleanup.stale || candidate.status !== 'done'} onClick={() => void choose('cleaned')}>Use cleaned wording</button>
      </div>}
    </>}
    {cleanup.status !== 'running' && <p className="subtle">Wording-check scope: this draft and {cleanup.snapshot.passage_count} recent accepted passages; three occurrences trigger a phrase match. {cleanup.snapshot.limited ? 'The history scan reached its size limit. ' : ''}Only flagged spans are eligible.</p>}
    <details><summary>Cleanup request details</summary><pre>{JSON.stringify({ algorithm: cleanup.snapshot.algorithm, eligible_spans: cleanup.snapshot.evidence, usage: cleanup.usage }, null, 2)}</pre></details>
    <ErrorNotice message={action.error} />
  </section>
}

function changeLabel(count: number) { return `${count} wording ${count === 1 ? 'change' : 'changes'}.` }
function canChooseCleanup(candidate: Candidate) { return !candidate.accepted_node_id && !candidate.text_edit }

function CleanupStop({ candidate, busy, stop }: { candidate: Candidate; busy: boolean; stop: () => void }) {
  return candidate.cleanup?.status === 'running' && candidate.status === 'done' ? <button className="button" disabled={busy} onClick={stop}>Stop cleanup</button> : null
}

function cleanupMessage(cleanup: Cleanup, edited: boolean) {
  if (edited) return 'An author revision is selected. This cleanup compares the preserved model draft.'
  if (cleanup.stale) return 'The path or draft changed. Cleanup cannot be applied; the original is shown.'
  if (cleanup.status === 'running') return 'Polishing flagged wording. Your original draft is saved.'
  if (cleanup.status === 'done') return cleanup.selected === 'cleaned' ? 'Showing cleaned wording.' : cleanup.edits.length ? 'Cleaned wording is available. Your original is still shown.' : 'Showing original wording.'
  return cleanup.error || 'Cleanup did not change this draft.'
}

function CleanupComparison({ cleanup }: { cleanup: Cleanup }) {
  return <details className="cleanup-comparison"><summary>Compare original and cleaned wording</summary>
    <ul>{cleanup.edits.map(edit => <li key={edit.start}><del>{originalWords(cleanup.snapshot.original, edit.start, edit.end)}</del> → <ins>{edit.text}</ins></li>)}</ul>
    <div className="cleanup-versions"><section><h4>Original draft</h4><div className="prose">{cleanup.snapshot.original}</div></section><section><h4>Cleaned draft</h4><div className="prose">{cleanup.cleaned}</div></section></div>
  </details>
}
