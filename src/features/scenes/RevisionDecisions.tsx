import { useState } from 'react'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { ModelProfile } from '../models/types'
import type { RevisionPlan, TriageItem } from './revisionTypes'
import { consolidatedScene, type SceneRun } from './types'
import { EvidenceList, TriageText } from './RevisionArtifact'
import { RevisionJobs } from './RevisionJobs'
import { ResolutionEditor } from './ResolutionEditor'
import { RevisionGate } from './RevisionGate'

export function RevisionDecisions({ run, plan, profiles }: { run: SceneRun; plan: RevisionPlan; profiles: ModelProfile[] }) {
  return <div className="form-stack"><h4>Your revision decisions</h4><p>{plan.summary}</p>
    {plan.approach === 'redraft' && <p role="status" className="scene-notice">This triage recommends a redraft. Return to Scene draft; the next request will include this triage and your saved resolutions. A revision package cannot be approved for this result.</p>}
    {plan.items.map((item) => <DecisionItem key={`${run.state.selections['scene-triage']}:${item.id}`} run={run} plan={plan} item={item} profiles={profiles} />)}
    {!plan.items.length && <p className="subtle">The selected reports contain no findings. You can explicitly approve a package with no changes.</p>}
    <RevisionGate key={`${run.id}:${run.state.gate_b?.approved_at ?? run.revision}`} run={run} plan={plan} />
  </div>
}

function DecisionItem({ run, plan, item, profiles }: { run: SceneRun; plan: RevisionPlan; item: TriageItem; profiles: ModelProfile[] }) {
  const [verifying, setVerifying] = useState(false)
  const verdict = plan.verifications[item.id]
  return <article className="review-finding form-stack"><TriageText item={item} />
    <details className="input-inspector"><summary>Original findings · {item.finding_ids.length}</summary>{plan.findings.filter((finding) => item.finding_ids.includes(finding.id)).map((finding) => <div key={finding.id}><h4>{finding.role} · {finding.severity}</h4><blockquote>{finding.quote}</blockquote><p>{finding.explanation}</p><p>{finding.suggestion}</p><small>{finding.id} · {finding.source_id}</small></div>)}</details>
    {verdict && <div className="scene-notice"><strong>Selected verdict: {verdict.verdict}</strong><p>{verdict.summary}</p><EvidenceList evidence={verdict.evidence} /><p>{verdict.smallest_fix}</p><small>Record your resolution separately before approving changes.</small></div>}
    <div className="scene-actions"><ResolveControl run={run} item={item} />{!consolidatedScene(run) && <button className="button quiet" aria-expanded={verifying} onClick={() => setVerifying(!verifying)}>{verifying ? 'Close verification' : `Verify ${item.id}`}</button>}</div>
    {verifying && <RevisionJobs run={run} profiles={profiles} step="scene-verify" targets={{ item_id: item.id }} />}
  </article>
}

function ResolveControl({ run, item }: { run: SceneRun; item: TriageItem }) {
  const [editing, setEditing] = useState<{ run: SceneRun; plan: RevisionPlan; item: TriageItem } | null>(null)
  const action = useAction()
  const open = () => action.run(async () => {
    const fresh = await api<SceneRun>(`/scenes/${run.id}`)
    const current = fresh.revision_plan?.items.find((value) => value.id === item.id)
    if (!fresh.revision_plan || !current || fresh.state.selections['scene-triage'] !== run.state.selections['scene-triage']) throw new Error('The selected triage changed. Review the updated decisions before editing.')
    setEditing({ run: fresh, plan: fresh.revision_plan, item: current })
  })
  return <><button className="button" aria-disabled={action.busy} disabled={run.stale} onClick={open}>Resolve {item.id}</button><ErrorNotice message={action.error} />{editing && <ResolutionEditor {...editing} onClose={() => setEditing(null)} />}</>
}
