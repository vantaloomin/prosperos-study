import { lazy, Suspense, useState } from 'react'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { ApiError } from '../../api'
import { CandidateView } from './CandidateView'
import { useGeneration } from './useGeneration'
import { isWorking, type Generation } from './types'
const GenerationReview = lazy(() => import('./GenerationReview').then(module => ({ default: module.GenerationReview })))

export function InlineGeneration({ id, onDismiss, onBranch, onCurrentSettings }: { id: string; onDismiss: () => void; onBranch: (id: string) => void; onCurrentSettings: () => void }) {
  const query = useGeneration(id)
  const [expanded, setExpanded] = useState(false)
  const generation = query.data
  const working = generation?.candidates.some(isWorking) ?? false
  return <section className="inline-draft" aria-label="Unaccepted draft" data-draft-id={id}>
    <header><div><span className="eyebrow">DRAFT · NOT YET IN YOUR STORY</span><p>Keep a telling when it feels right.</p></div><button className="text-button" onClick={onDismiss} disabled={working}>Dismiss</button></header>
    {query.error && <DraftConnectionError error={query.error} onCheck={() => void query.refetch()} />}
    {!generation && !query.error && <Loading label="Opening saved draft…" />}
    {generation && <DraftContent generation={generation} onBranch={onBranch} onDismiss={onDismiss} onExpand={() => setExpanded(true)} onCurrentSettings={onCurrentSettings} />}
    {expanded && <Suspense fallback={<Loading label="Opening details…" />}><GenerationReview id={id} onBranch={onBranch} onClose={() => setExpanded(false)} /></Suspense>}
  </section>
}

function DraftConnectionError({ error, onCheck }: { error: Error; onCheck: () => void }) {
  const message = error instanceof ApiError ? error.message : 'Connection to the app lost; the request’s status is unknown. Your draft has not been resent.'
  return <div className="request-recovery"><ErrorNotice message={message} /><button className="button" onClick={onCheck}>Check request status</button></div>
}

function DraftContent({ generation, onBranch, onDismiss, onExpand, onCurrentSettings }: { generation: Generation; onBranch: (id: string) => void; onDismiss: () => void; onExpand: () => void; onCurrentSettings: () => void }) {
  const [selected, setSelected] = useState('')
  const candidate = generation.candidates.find(item => item.id === selected) ?? generation.candidates[0]
  if (!candidate) return null
  const failed = ['error', 'cancelled', 'interrupted'].includes(candidate.status)
  return <><div className="candidate-tabs" aria-label="Draft alternatives">{generation.candidates.map((item, index) => <button key={item.id} aria-pressed={item.id === candidate.id} className={item.id === candidate.id ? 'active' : ''} onClick={() => setSelected(item.id)}>{item.profile.name} · {index + 1}</button>)}</div>
    <CandidateView candidate={candidate} generation={generation} onBranch={onBranch} onClose={onDismiss} onAlternate={setSelected} />
    <div className="inline-draft-tools"><button className="text-button" onClick={onExpand}>Expand & inspect inputs</button>{failed && <button className="text-button" onClick={onCurrentSettings}>Try with current settings…</button>}</div></>
}
