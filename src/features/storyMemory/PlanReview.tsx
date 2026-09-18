import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { ModelChoices } from '../authoring/AuthoringModels'
import { readyProfiles } from '../models/profileReadiness'
import type { ProfileList } from '../models/types'
import { PromptEditor, type Prompt } from '../prompts/Prompts'
import type { ContinuityChange } from '../scenes/continuityTypes'
import type { PlanView } from './planTypes'
import type { PlanReviewPreview } from './planReviewTypes'
import { PlanReviewResults } from './PlanReviewResults'

interface Props { branchId: string; storyId: string; view: PlanView; onClose: () => void; onChoose: (change: ContinuityChange) => void }
export function PlanReview({ branchId, storyId, view, onClose, onChoose }: Props) {
  const [runId, setRunId] = useState('')
  const history = useQuery({ queryKey: ['plan-reviews', branchId], queryFn: () => api<{ id: string; created_at: string; passages: number }[]>('/branches/' + branchId + '/plan-reviews') })
  return <Modal open onClose={onClose} title="Review plans & commitments" wide
    description="An optional reading of accepted prose. Suggestions stay separate until you review and save them.">
    <div className="dialog-body form-stack">
      <ErrorNotice message={history.error?.message} />
      {runId ? <><button className="text-button" onClick={() => setRunId('')}>Back to review setup</button><PlanReviewResults id={runId} view={view} onChoose={onChoose} /></>
        : <PlanReviewSetup branchId={branchId} storyId={storyId} revision={view.revision} onStarted={setRunId} />}
      {!!history.data?.length && <details><summary>Saved plan suggestions ({history.data.length})</summary><div className="form-stack authoring-history">
        {history.data.map(run => <button className="button" key={run.id} onClick={() => setRunId(run.id)}>{new Date(run.created_at).toLocaleString()} · {run.passages} passages</button>)}
      </div></details>}
    </div>
  </Modal>
}

function PlanReviewSetup({ branchId, storyId, revision, onStarted }: { branchId: string; storyId: string; revision: number; onStarted: (id: string) => void }) {
  const [limit, setLimit] = useState(4)
  const [range, setRange] = useState('next')
  const [compare, setCompare] = useState(false)
  const [profiles, setProfiles] = useState<string[]>([])
  const [prepared, setPrepared] = useState<PlanReviewPreview | null>(null)
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const requestId = useRef(operationId())
  const frozenStart = useRef<object | null>(null)
  const action = useAction()
  const models = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const change = (update: () => void) => { update(); setPrepared(null); frozenStart.current = null; requestId.current = operationId() }
  const request = { expected_revision: revision, limit, from_beginning: range === 'beginning', latest_only: range === 'latest', profile_ids: profiles }
  const preview = () => action.run(async () => {
    const next = await api<PlanReviewPreview>('/branches/' + branchId + '/plan-reviews/preview', request)
    setPrepared(next); requestId.current = operationId()
    frozenStart.current = { ...request, operation_id: requestId.current, preview_hash: next.preview_hash }
  })
  const start = () => action.run(async () => {
    const run = await api<{ id: string }>('/branches/' + branchId + '/plan-reviews', frozenStart.current)
    onStarted(run.id)
  })
  const editPrompt = () => action.run(async () => {
    const prompts = await api<Prompt[]>('/prompts?story_id=' + storyId)
    setPrompt(prompts.find(item => item.key === 'scene-continuity') ?? null)
  })
  return <section className="form-stack">
    <p>Review the next unreviewed batch on this branch. Completed excerpts are remembered, including when you skip ahead. Suggestions still need your approval. Nothing runs automatically after a response.</p>
    <label className="field"><span>Passages per review</span><select aria-label="Passages per review" disabled={range === 'latest'} value={limit} onChange={event => change(() => setLimit(Number(event.target.value)))}>{[1, 2, 4, 8].map(count => <option key={count}>{count}</option>)}</select></label>
    <label className="field"><span>Which accepted prose?</span><select aria-label="Which accepted prose?" value={range} onChange={event => change(() => setRange(event.target.value))}>
      <option value="next">Next unreviewed batch</option><option value="latest">Latest excerpt only</option><option value="beginning">Review from the beginning</option>
    </select></label>
    {models.data && <ModelChoices profiles={models.data.profiles} selected={profiles} compare={compare}
      onMode={value => change(() => { setCompare(value); setProfiles([]) })} onChange={value => change(() => setProfiles(value))} />}
    <details><summary>Continuity role instructions</summary><p className="subtle">Uses the existing Continuity proposals role, its enabled state, and the saved model for this step. Its default is Primary Writer.</p><button className="text-button" onClick={editPrompt}>Edit continuity instructions</button></details>
    <ErrorNotice message={action.error || models.error?.message} />
    <button className="button" disabled={action.busy || (compare && (profiles.length < 2 || profiles.length > 4))} onClick={preview}>Preview plan review</button>
    {prepared && <div className="prepared-card form-stack"><p>{prepared.passages.length} accepted excerpts · {prepared.remaining_passages} remain unreviewed after this batch · {prepared.request_count} model request(s)</p>
      {prepared.omitted_plans > 0 && <p role="status">{prepared.omitted_plans} existing plans do not fit. Indirect references may remain ambiguous.</p>}
      {prepared.jobs.map((job, index) => <p key={index}>{job.profile_name} · {job.model} · prompt v{job.prompt_version} · approximately {job.estimated_input_tokens.toLocaleString()} input tokens</p>)}
      <details><summary>Read the passages being sent</summary>{prepared.passages.map(source => <article key={source.id}><h4>{source.title}</h4><pre className="authoring-prose">{source.text}</pre></article>)}</details>
      <button className="button primary" disabled={action.busy} onClick={start}>Suggest plan changes</button>
    </div>}
    {prompt && <PromptEditor prompt={prompt} storyId={storyId} onClose={() => { setPrompt(null); setPrepared(null) }} />}
  </section>
}
