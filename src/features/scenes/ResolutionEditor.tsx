import { useState } from 'react'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import { dispositions, type Evidence, type Resolution, type RevisionPlan, type Source, type TriageItem } from './revisionTypes'
import { consolidatedScene, type SceneRun } from './types'

export function ResolutionEditor({ run, plan, item, onClose }: { run: SceneRun; plan: RevisionPlan; item: TriageItem; onClose: () => void }) {
  const [revision] = useState(run.revision)
  const key = `roleplay:resolution:${run.id}:${run.state.selections['scene-triage']}:${item.id}`
  const [draft, setDraft] = usePersistent<Resolution>(key, { disposition: item.disposition, reason: item.reason, action: item.action, evidence: item.evidence })
  const action = useAction()
  const save = () => action.run(async () => {
    await api(`/scenes/${run.id}/resolve`, { operation_id: operationId(), expected_revision: revision, item_id: item.id, resolution: draft })
    localStorage.removeItem(key)
    onClose()
  })
  const verdict = plan.verifications[item.id]
  return <Modal open onClose={onClose} title={`Resolve ${item.id}`} description="Record your reason and proposed action. This changes the revision plan, not Story text." wide><div className="dialog-body form-stack">
    <label className="field"><span>Disposition</span><select value={draft.disposition} onChange={(event) => setDraft({ ...draft, disposition: event.target.value as Resolution['disposition'] })}>{dispositions.filter(value => !consolidatedScene(run) || value !== 'verify').map((value) => <option key={value}>{value}</option>)}</select></label>
    <label className="field"><span>Reason</span><textarea rows={3} maxLength={4000} value={draft.reason} onChange={(event) => setDraft({ ...draft, reason: event.target.value })} /></label>
    <label className="field"><span>Proposed action</span><textarea rows={3} maxLength={4000} value={draft.action} onChange={(event) => setDraft({ ...draft, action: event.target.value })} /></label>
    <p className="subtle">Hard fixes cannot silently become optional. An overrule needs exact source evidence. Check the supplied sources and record your resolution. Undecidable items block package approval until you resolve them.</p>
    {verdict && <button className="button quiet" onClick={() => setDraft({ ...draft, evidence: verdict.evidence })}>Use selected verdict’s evidence</button>}
    <EvidenceEditor sources={plan.sources} evidence={draft.evidence} onChange={(evidence) => setDraft({ ...draft, evidence })} />
    <ErrorNotice message={action.error} /></div><footer className="dialog-footer"><span className="subtle">Saving a resolution clears any earlier package approval.</span><button className="button primary" disabled={action.busy || !draft.reason.trim()} onClick={save}>Save resolution</button></footer></Modal>
}

function EvidenceEditor({ sources, evidence, onChange }: { sources: Source[]; evidence: Evidence[]; onChange: (next: Evidence[]) => void }) {
  const update = (index: number, item: Evidence) => onChange(evidence.map((value, position) => position === index ? item : value))
  return <div className="form-stack"><h4>Cited evidence</h4>{evidence.map((item, index) => <fieldset className="scene-beat-editor form-stack" key={index}><legend>Evidence {index + 1}</legend><label className="field"><span>Source</span><select value={item.source_id} onChange={(event) => update(index, { ...item, source_id: event.target.value, quote: '' })}>{sources.map((source) => <option key={source.id} value={source.id}>{source.title} · {source.kind}</option>)}</select></label><details className="input-inspector"><summary>Read this frozen source</summary><pre>{sources.find((source) => source.id === item.source_id)?.text}</pre></details><label className="field"><span>Exact quotation</span><textarea rows={3} maxLength={4000} value={item.quote} onChange={(event) => update(index, { ...item, quote: event.target.value })} /></label><button className="text-button" onClick={() => onChange(evidence.filter((_, position) => position !== index))}>Remove evidence {index + 1}</button></fieldset>)}<button className="button quiet" disabled={evidence.length >= 10 || !sources.length} onClick={() => onChange([...evidence, { source_id: sources[0].id, quote: '' }])}>Add source evidence</button></div>
}
