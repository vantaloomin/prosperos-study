import { lazy, Suspense, useState } from 'react'
import { Loading } from '../../components/Feedback'
import { PlanDetails } from './PlanDetails'
import type { ContinuityChange } from '../scenes/continuityTypes'
import type { PlanEntry, PlanView } from './planTypes'
const PlanEditor = lazy(() => import('./PlanEditor').then(module => ({ default: module.PlanEditor })))

const PlanReview = lazy(() => import('./PlanReview').then(module => ({ default: module.PlanReview })))

export function PlanManager({ branchId, storyId, view, onReadMessage }: { branchId: string; storyId: string; view: PlanView; onReadMessage: (id: string) => void }) {
  const [editing, setEditing] = useState<PlanEntry | 'new' | null>(null)
  const [reviewing, setReviewing] = useState(false)
  const [suggestion, setSuggestion] = useState<ContinuityChange | undefined>(undefined)
  const plans = view.entries.filter((entry): entry is PlanEntry => !!entry.plan)
  return <section className="form-stack plan-manager" aria-label="Plans and commitments">
    <div className="section-heading"><h3>Plans & commitments</h3><button className="text-button" onClick={() => { setSuggestion(undefined); setEditing('new') }}>Add plan</button></div>
    <button className="text-button plan-review-launch" onClick={() => setReviewing(true)}>Review plans</button>
    <p className="subtle">What is intended, promised, or still unfinished on this path.</p>
    {plans.map(entry => <details className="context-asset" key={entry.id}>
      <summary><span>{entry.subject}<small>{entry.plan.status} · {entry.plan.timing}</small></span></summary>
      <div className="form-stack"><PlanDetails plan={entry.plan} /><p>{entry.text}</p>
        <button className="button" onClick={() => { setSuggestion(undefined); setEditing(entry) }}>Update plan</button>
        <button className="text-button" onClick={() => onReadMessage(entry.node_id)}>Read the recorded passage</button>
        <details><summary>Supporting evidence</summary>{entry.evidence.map((evidence, index) => <blockquote key={index}>{evidence.quote}</blockquote>)}</details>
      </div>
    </details>)}
    {!plans.length && <p className="subtle">No plans recorded yet. Start with an agreement or intention already in the story.</p>}
    {editing && <Suspense fallback={<Loading label="Opening plan…" />}><PlanEditor branchId={branchId} view={view} suggestion={suggestion} entry={editing === 'new' ? undefined : editing} onClose={() => setEditing(null)} /></Suspense>}
    {reviewing && <Suspense fallback={<Loading label="Opening plan review…" />}><PlanReview branchId={branchId} storyId={storyId} view={view} onClose={() => setReviewing(false)} onChoose={change => {
      setReviewing(false); setSuggestion(change); setEditing(plans.find(entry => entry.id === change.target_id) ?? 'new')
    }} /></Suspense>}
  </section>
}
