import { useState } from 'react'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { SceneRun } from './types'

export function ManualSceneAcceptance({ run, onBranch }: { run: SceneRun; onBranch: (id: string) => void }) {
  if (run.state.accepted?.manual_review) return <section className="scene-notice form-stack"><h3>Scene accepted after your review</h3><p>The selected prose is saved. Skipped agents remain recorded; existing continuity is preserved.</p><button className="button primary" onClick={() => onBranch(run.state.accepted!.branch_id)}>Read accepted scene</button></section>
  if (run.state.accepted || !run.manual_acceptance) return null
  return <ManualAcceptanceEditor key={run.revision} run={run} />
}

function ManualAcceptanceEditor({ run }: { run: SceneRun }) {
  const material = run.manual_acceptance!
  const [reviewed, setReviewed] = useState(false)
  const [branch, setBranch] = useState(run.stale)
  const action = useAction()
  const accept = () => action.run(async () => {
    await api(`/scenes/${run.id}/accept`, { operation_id: operationId(), expected_revision: run.revision,
      manual_review: true, as_new_branch: branch, branch_name: 'Manually reviewed scene' })
  })
  return <section className="scene-gate form-stack"><h3>Accept after your own review</h3>
    <p>Some agents were disabled for this scene. Review the selected prose yourself before adding it to the Story. Existing continuity stays in place; no generated facts or summary will be added.</p>
    <details className="input-inspector"><summary>Skipped agents</summary><ul>{material.disabled_steps.map((key) => <li key={key}>{key.replace(/^scene-|^review-/, '').replaceAll('-', ' ')}</li>)}</ul></details>
    <details className="input-inspector" open><summary>{material.source}</summary><pre>{material.text}</pre></details>
    <label className="check-row"><input type="checkbox" checked={branch} disabled={run.stale} onChange={(event) => setBranch(event.target.checked)} />Accept on a new branch from this scene's starting point</label>
    {run.stale && <p className="subtle">The Story changed, so this scene will start a new branch.</p>}
    <label className="check-row"><input type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />I reviewed this prose, including any incomplete revisions, and accept it with the skipped checks</label>
    <ErrorNotice message={action.error} /><button className="button primary" disabled={action.busy || !reviewed} onClick={accept}>Accept manually reviewed scene</button>
  </section>
}
