import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { ContinuityChange } from '../scenes/continuityTypes'
import { PlanDetails } from './PlanDetails'
import type { PlanReviewJob, PlanReviewRun } from './planReviewTypes'
import type { PlanView } from './planTypes'

const working = (job: PlanReviewJob) => job.status === 'queued' || job.status === 'running'
export function PlanReviewResults({ id, view, onChoose }: { id: string; view: PlanView; onChoose: (change: ContinuityChange) => void }) {
  const [selected, setSelected] = useState('')
  const query = useQuery({ queryKey: ['plan-review', id], queryFn: () => api<PlanReviewRun>('/reviews/' + id),
    refetchInterval: state => state.state.data?.jobs.some(working) ? 1000 : false })
  const job = query.data?.jobs.find(item => item.id === selected) ?? query.data?.jobs[0]
  if (query.isPending) return <Loading label="Opening plan suggestions…" />
  return <section className="form-stack"><ErrorNotice message={query.error?.message} />
    <p className="subtle">These suggestions cannot change prose or plans on their own. Review a suggestion in the plan editor before saving it.</p>
    {query.data?.snapshot.branch.revision !== view.revision && <p role="status">This branch has changed since the review. Compare each suggestion with the current plan before saving.</p>}
    <div className="review-job-tabs">{query.data?.jobs.map(item => <button key={item.id} aria-pressed={item.id === job?.id} onClick={() => setSelected(item.id)}>{item.snapshot.profile.name} · {item.status}</button>)}</div>
    {job && <PlanReport key={job.id} job={job} view={view} onChoose={onChoose} />}
  </section>
}
function PlanReport({ job, view, onChoose }: { job: PlanReviewJob; view: PlanView; onChoose: (change: ContinuityChange) => void }) {
  const action = useAction()
  const control = (operation: 'cancel' | 'retry') => action.run(async () => { await api('/review-jobs/' + job.id + '/' + operation, {}) })
  return <div className="form-stack"><p role="status">{job.status} · attempt {job.attempt}</p><ErrorNotice message={action.error || job.error} />
    {job.result && <><p>{job.result.summary}</p>{!job.result.changes.length && <p>No plan changes were proposed.</p>}
      {job.result.changes.map(change => <PlanSuggestion key={change.id} change={change} view={view} onChoose={onChoose} />)}</>}
    {working(job) && <button className="button" disabled={action.busy} onClick={() => control('cancel')}>Stop plan review</button>}
    {!working(job) && job.status !== 'done' && <button className="button" disabled={action.busy} onClick={() => control('retry')}>Retry original plan inputs</button>}
    <details><summary>Original inputs and response</summary><p>Prompt v{job.snapshot.prompt.number} · {job.snapshot.profile.config.model}</p><pre className="authoring-prose">{job.snapshot.prompt.template}</pre><pre className="authoring-prose">{job.snapshot.content}</pre><pre className="authoring-prose">{job.output || 'No response text yet.'}</pre></details>
  </div>
}

function PlanSuggestion({ change, view, onChoose }: { change: ContinuityChange; view: PlanView; onChoose: (change: ContinuityChange) => void }) {
  const represented = view.entries.some(entry => entry.subject === change.subject && entry.text === change.text && JSON.stringify(entry.plan) === JSON.stringify(change.plan))
  const missing = !!change.target_id && !view.entries.some(entry => entry.id === change.target_id)
  return <article className="prepared-card form-stack"><h3>{change.subject}</h3>{change.plan && <PlanDetails plan={change.plan} />}
    <p>{change.text}</p><p className="subtle">{change.reason}</p>
    {change.evidence.map((citation, index) => <blockquote key={index}>{citation.quote}</blockquote>)}
    <button className="button" disabled={represented || missing} onClick={() => onChoose(change)}>{represented ? 'Already reflected in this path' : 'Review this suggestion'}</button>
    {missing && <p className="subtle">The plan this suggestion would change is not present on this path.</p>}
  </article>
}
