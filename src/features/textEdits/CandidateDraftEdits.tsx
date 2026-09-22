import { lazy, Suspense, useRef, useState } from 'react'
import type { Candidate, Generation } from '../generation/types'
import type { EditInitial, TextTarget } from './types'
const TextEditWindow = lazy(() => import('./TextEditWindow').then(module => ({ default: module.TextEditWindow })))

export function CandidateDraftEdits({ candidate, generation, onBranch }: { candidate: Candidate; generation: Generation; onBranch: (id: string) => void }) {
  const [view, setView] = useState<EditInitial | null>(null)
  const trigger = useRef<HTMLElement | null>(null)
  if (candidate.status !== 'done') return null
  const target: TextTarget = { kind: 'candidate', story_id: generation.snapshot.branch.story_id, branch_id: generation.branch_id, candidate_id: candidate.id }
  const open = (initial: EditInitial, button: HTMLElement) => { trigger.current = button; setView(initial) }
  const revise = (button: HTMLElement, replacement?: string) => open({ target, replacement, expectedVersion: candidate.wording_version ?? undefined }, button)
  return <section className="form-stack" aria-label="Author draft revisions">
    {candidate.text_edit && <><p className="subtle">Showing author revision {candidate.text_edit.revision}. {candidate.accepted_node_id ? 'This wording was kept in the Story.' : 'This text is still a draft.'}</p><details><summary>Preserved model draft</summary><div className="prose">{candidate.output}</div></details><button className="text-button" onClick={event => open({ receiptId: candidate.text_edit!.receipt_id }, event.currentTarget)}>View draft change and Undo</button></>}
    {!candidate.accepted_node_id && <DraftEditChoices candidate={candidate} onReview={revise} />}
    {view && <Suspense fallback={<span role="status">Opening draft revision…</span>}><TextEditWindow initial={view} onBranch={onBranch} onClose={() => setView(null)} focusOnClose={() => trigger.current} /></Suspense>}
  </section>
}

function DraftEditChoices({ candidate, onReview }: { candidate: Candidate; onReview: (button: HTMLElement, replacement?: string) => void }) {
  const cleaned = candidate.cleanup?.status === 'done' && !candidate.cleanup.stale
  return <div className="text-edit-actions"><button className="button" onClick={event => onReview(event.currentTarget)}>Edit this draft</button>{candidate.text_edit && <><button className="text-button" onClick={event => onReview(event.currentTarget, candidate.output)}>Review original wording</button>{cleaned && <button className="text-button" onClick={event => onReview(event.currentTarget, candidate.cleanup!.cleaned)}>Review cleaned wording</button>}</>}</div>
}
