import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch } from '../../types'
import type { ModelProfile } from '../models/types'
import { ReviewResults } from '../workflow/ReviewResults'
import { ReviewEstimate, ReviewRoles } from '../workflow/ReviewSetup'
import { defaultReviewSteps, type ReviewHistoryItem, type ReviewPreview, type ReviewRequest, type Routing } from '../workflow/types'
import type { SceneRun } from './types'

type Props = { run: SceneRun; branch: Branch; routing: Routing; profiles: ModelProfile[] }

export function SceneReviews(props: Props) {
  const { run } = props
  const [selected, setSelected] = usePersistent(`roleplay:scene-review:${run.id}`, '')
  const [compose, setCompose] = useState(false)
  const covered = run.coverage_passes || run.snapshot.disabled_steps?.includes('scene-coverage')
  const ready = covered && !!run.draft?.complete && !run.stale
  const started = (id: string) => { setSelected(id); setCompose(false) }
  return <section className="scene-reviews form-stack"><div><h3>Independent readers</h3><p className="subtle">Invite specialists to review this saved draft before it becomes Story text. Reports stay attached to the exact draft they read; choosing another draft preserves the earlier reports.</p></div>
    {!ready && <p className="subtle">Complete the selected draft and its beat coverage on the current Story before requesting a review.</p>}
    <button className="button" disabled={!ready} aria-expanded={compose} onClick={() => setCompose(!compose)}>{compose ? 'Close review setup' : 'Review this saved draft'}</button>
    {compose && ready && <SceneReviewSetup key={`${run.id}:${run.revision}`} {...props} onStarted={started} />}
    <SceneReviewHistory {...props} selected={selected} onSelect={setSelected} />
  </section>
}

function SceneReviewHistory({ run, branch, routing, selected, onSelect }: Props & { selected: string; onSelect: (id: string) => void }) {
  const history = useQuery({ queryKey: ['reviews', branch.id, 'scene', run.id], queryFn: () => api<ReviewHistoryItem[]>(`/branches/${branch.id}/reviews?scene_id=${run.id}`) })
  const records = history.data ?? []
  const current = records.find((item) => item.id === selected) ?? records[0]
  return <><ErrorNotice message={history.error?.message} />
    {!!records.length && <label className="field"><span>Reviews of this scene</span><select value={current?.id ?? ''} onChange={(event) => onSelect(event.target.value)}>{records.map((item, index) => <option key={item.id} value={item.id}>Review {records.length - index} · {new Date(item.created_at).toLocaleString()}</option>)}</select></label>}
    {current && <ReviewResults key={current.id} id={current.id} branch={branch} steps={routing.steps} />}
  </>
}

function SceneReviewSetup({ run, branch, routing, profiles, onStarted }: Props & { onStarted: (id: string) => void }) {
  const [steps, setSteps] = usePersistent(`roleplay:scene-review-roles:${run.id}`, defaultReviewSteps)
  const [preview, setPreview] = useState<{ body: ReviewRequest; data: ReviewPreview; operation: string } | null>(null)
  const action = useAction()
  const endpoint = `/branches/${branch.id}/reviews`
  const prepare = () => action.run(async () => {
    const body = { expected_revision: branch.revision, scene_id: run.id, scene_revision: run.revision, steps }
    const data = await api<ReviewPreview>(`${endpoint}/preview`, body)
    setPreview({ body, data, operation: operationId() })
  })
  const start = () => action.run(async () => {
    if (!preview) return
    const result = await api<{ id: string }>(endpoint, { ...preview.body, preview_hash: preview.data.preview_hash, operation_id: preview.operation })
    onStarted(result.id)
  })
  return <div className="form-stack"><p className="subtle">Blind readers receive only the draft and at most two preceding prose contributions. Rules and continuity reviewers receive their permitted frozen references. Other reports and coverage judgments are excluded.</p>
    <ReviewRoles routing={routing} profiles={profiles} steps={steps} onChange={(value) => { setSteps(value); setPreview(null) }} />
    <ErrorNotice message={action.error} /><button className="button" disabled={action.busy || !steps.length} onClick={prepare}>Preview draft review requests</button>
    {preview && <ReviewEstimate data={preview.data} busy={action.busy} onStart={start} />}
  </div>
}
