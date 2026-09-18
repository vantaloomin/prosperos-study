import { useState } from 'react'
import { PlanDetails } from '../storyMemory/PlanDetails'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { ModelProfile } from '../models/types'
import type { ContinuityChange } from './continuityTypes'
import { RevisionJobs } from './RevisionJobs'
import type { SceneResult, SceneRun } from './types'
import { useSceneFocus } from './useSceneFocus'

export function ContinuityArtifact({ result }: { result: SceneResult }) {
  return <div className="form-stack"><p>{result.summary}</p><h4>Proposed scene summary</h4><p>{result.scene_summary}</p>
    <details className="input-inspector"><summary>Summary evidence</summary><blockquote>{result.summary_quote}</blockquote></details>
    {result.changes?.map((change) => <ContinuityChangeView key={change.id} change={change} />)}
    {!result.changes?.length && <p className="subtle">No changes to branch continuity are proposed.</p>}
  </div>
}

function ContinuityChangeView({ change }: { change: ContinuityChange }) {
  return <article className="review-finding"><span className="eyebrow">{change.action} · {change.kind}</span><h4>{change.subject}</h4><p>{change.text}</p><p className="subtle">{change.reason}</p>{change.plan && <PlanDetails plan={change.plan} />}
    <details className="input-inspector"><summary>Evidence for this change</summary>{change.evidence.map((item, index) => <div key={index}><blockquote>{item.quote}</blockquote><small>{item.source_id}</small></div>)}</details>
  </article>
}

export function ContinuityWorkspace({ run, profiles, onBranch }: { run: SceneRun; profiles: ModelProfile[]; onBranch: (id: string) => void }) {
  const focus = useSceneFocus(run.state.accepted ? 'scene-accepted' : 'continuity')
  if (run.state.accepted?.manual_review || run.snapshot.disabled_steps?.includes('scene-continuity')) return null
  if (!run.patch?.checked) return null
  if (run.state.accepted) return <section ref={focus} tabIndex={-1} className="scene-notice form-stack"><h3>Scene accepted</h3><p>The checked prose and your selected continuity were saved together. Earlier paths and shared Library versions are preserved.</p><button className="button primary" onClick={() => onBranch(run.state.accepted!.branch_id)}>Read accepted scene</button></section>
  return <section ref={focus} tabIndex={-1} className="scene-revisions form-stack"><h3>What becomes part of the Story</h3><p>Ask the continuity scribe to identify established facts, character knowledge and thread changes. Its proposals remain separate until you accept the scene.</p>
    <details className="input-inspector"><summary>Continuity proposals and comparisons</summary><RevisionJobs run={run} step="scene-continuity" profiles={profiles} targets={{}} /></details>
    {run.continuity_proposal && <AcceptanceEditor key={run.state.selections['scene-continuity']} run={run} />}
  </section>
}

function AcceptanceEditor({ run }: { run: SceneRun }) {
  const proposal = run.continuity_proposal!
  const [selection, setSelection] = usePersistent(`roleplay:scene-acceptance:${run.id}:${run.state.selections['scene-continuity']}`, { ids: [] as string[], summary: false, note: '', branch: false, name: 'Accepted scene' })
  const [reviewed, setReviewed] = useState(false)
  const action = useAction()
  const toggle = (id: string, checked: boolean) => setSelection({ ...selection, ids: checked ? [...selection.ids, id] : selection.ids.filter((value) => value !== id) })
  const accept = () => action.run(async () => {
    await api(`/scenes/${run.id}/accept`, { operation_id: operationId(), expected_revision: run.revision,
      selected_ids: selection.ids, include_summary: selection.summary, note: selection.note,
      as_new_branch: selection.branch, branch_name: selection.name })
  })
  return <div className="form-stack"><h4>Choose continuity to keep</h4><p className="subtle">Only checked items will be recorded. You may accept the prose without adding any structured continuity.</p>
    {proposal.changes.map((change) => <div key={change.id}><label className="check-row"><input type="checkbox" checked={selection.ids.includes(change.id)} onChange={(event) => toggle(change.id, event.target.checked)} />Keep {change.kind}: {change.subject}</label><ContinuityChangeView change={change} /></div>)}
    <label className="check-row"><input type="checkbox" checked={selection.summary} onChange={(event) => setSelection({ ...selection, summary: event.target.checked })} />Keep the scene summary</label><p>{proposal.scene_summary}</p>
    <details className="input-inspector"><summary>Final Story prose</summary><pre>{run.patch!.text}</pre></details>
    <label className="field"><span>Acceptance note (optional)</span><textarea rows={2} maxLength={5000} value={selection.note} onChange={(event) => setSelection({ ...selection, note: event.target.value })} /></label>
    <label className="check-row"><input type="checkbox" checked={selection.branch} onChange={(event) => setSelection({ ...selection, branch: event.target.checked })} />Accept on a new branch from this scene’s starting point</label>
    {selection.branch && <label className="field"><span>New branch name</span><input maxLength={120} value={selection.name} onChange={(event) => setSelection({ ...selection, name: event.target.value })} /></label>}
    {run.stale && <p role="status" className="scene-notice">The original Story has changed. A new branch is required to preserve this scene’s starting history and Library versions.</p>}
    <label className="check-row"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />I reviewed the final prose and selected continuity</label>
    <ErrorNotice message={action.error} /><button className="button primary" disabled={action.busy || !reviewed || (run.stale && !selection.branch) || (selection.branch && !selection.name.trim())} onClick={accept}>Accept scene · {selection.ids.length} continuity {selection.ids.length === 1 ? 'change' : 'changes'}</button>
  </div>
}
