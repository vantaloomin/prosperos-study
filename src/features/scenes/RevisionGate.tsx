import { useState } from 'react'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { RevisionPlan, TriageItem } from './revisionTypes'
import type { SceneRun } from './types'
import { useSceneFocus } from './useSceneFocus'

const names: Record<string, string> = { A: 'A · Canon and hard fixes', B: 'B · Add accepted suggestions and cuts', C: 'C · Add structural changes', custom: 'Custom · Choose individual changes' }

export function RevisionGate({ run, plan }: { run: SceneRun; plan: RevisionPlan }) {
  const [selection, setSelection] = useState('B')
  const [custom, setCustom] = useState<string[]>(plan.packages.B)
  const [confirmed, setConfirmed] = useState<string[]>([])
  const [note, setNote] = useState('')
  const action = useAction()
  const ids = selection === 'custom' ? custom : plan.packages[selection]
  const chosen = plan.items.filter((item) => ids.includes(item.id))
  const holds = chosen.filter((item) => item.disposition === 'hold')
  const pending = plan.items.some((item) => item.disposition === 'verify')
  const ready = !pending && plan.approach === 'patch' && holds.every((item) => confirmed.includes(item.id))
  const approve = () => action.run(async () => { await api(`/scenes/${run.id}/approve-revision`, { operation_id: operationId(), expected_revision: run.revision, package: selection, item_ids: selection === 'custom' ? custom : [], confirmed_hold_ids: confirmed, note }) })
  if (run.state.gate_b) return <ApprovedPackage run={run} />
  return <section className="scene-gate form-stack"><h4>Director approval · Revision package</h4><p>Choose the exact changes to authorize for the patching stage. This approval does not accept prose or update canon.</p>
    <label className="field"><span>Revision package</span><select value={selection} onChange={(event) => { setSelection(event.target.value); setConfirmed([]) }}>{Object.entries(names).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label>
    {selection === 'custom' && <div>{plan.items.filter((item) => !['verify', 'overrule'].includes(item.disposition)).map((item) => <label className="check-row" key={item.id}><input type="checkbox" checked={custom.includes(item.id)} disabled={mandatory(item, plan)} onChange={() => { setCustom(custom.includes(item.id) ? custom.filter((id) => id !== item.id) : [...custom, item.id]); setConfirmed([]) }} />{item.id} · {item.action}</label>)}</div>}
    <ul>{chosen.map((item) => <li key={item.id}>{item.id} · {item.action}</li>)}</ul>{!chosen.length && <p>No prose changes in this package.</p>}
    {holds.map((item) => <label className="check-row" key={item.id}><input type="checkbox" checked={confirmed.includes(item.id)} onChange={() => setConfirmed(confirmed.includes(item.id) ? confirmed.filter((id) => id !== item.id) : [...confirmed, item.id])} />I approve structural change {item.id}: {item.action}</label>)}
    {pending && <p role="status">Resolve disputed items before approving a package.</p>}
    <label className="field"><span>Revision approval note (optional)</span><textarea rows={2} maxLength={5000} value={note} onChange={(event) => setNote(event.target.value)} /></label>
    <ErrorNotice message={action.error} /><button className="button primary" disabled={action.busy || run.stale || !ready} onClick={approve}>Approve revision package</button>
  </section>
}

function mandatory(item: TriageItem, plan: RevisionPlan) {
  return item.disposition === 'hard-fix' || (item.disposition === 'hold' && plan.findings.some((finding) => item.finding_ids.includes(finding.id) && finding.severity === 'hard'))
}

function ApprovedPackage({ run }: { run: SceneRun }) {
  const focus = useSceneFocus('revision-approved')
  const gate = run.state.gate_b!
  return <section ref={focus} tabIndex={-1} role="status" className="scene-notice"><h4>Revision package approved · {gate.package}</h4><p>{new Date(gate.approved_at).toLocaleString()}</p><ul>{gate.items.map((item) => <li key={item.id}>{item.action}</li>)}</ul><p>{gate.note}</p><p>Story text is unchanged. The approved package is saved for the patching and verification stages.</p></section>
}
