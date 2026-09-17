import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { BeatPlan, SceneBeat, SceneRun } from './types'
import { ChanceEditor } from './SceneChance'

function focusBeat(id: string) {
  requestAnimationFrame(() => document.getElementById(`scene-beat-title-${id}`)?.focus())
}

export function BeatEditor({ run, plan, onClose, onSaved }: { run: SceneRun; plan: BeatPlan; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = usePersistent(`roleplay:beat-edit:${run.id}:${run.revision}`, plan)
  const action = useAction()
  const update = (id: string, change: Partial<SceneBeat>) => setDraft({ ...draft, beats: draft.beats.map((beat) => beat.id === id ? { ...beat, ...change } : beat) })
  const move = (index: number, offset: number) => {
    const beats = [...draft.beats]
    ;[beats[index], beats[index + offset]] = [beats[index + offset], beats[index]]
    setDraft({ ...draft, beats })
    focusBeat(draft.beats[index].id)
  }
  const remove = (id: string) => {
    const beats = draft.beats.filter((beat) => beat.id !== id)
    setDraft({ ...draft, beats })
    focusBeat(beats[0].id)
  }
  const save = () => action.run(async () => {
    await api(`/scenes/${run.id}/edit`, { operation_id: operationId(), expected_revision: run.revision, plan: draft })
    onSaved()
  })
  const add = () => {
    const id = crypto.randomUUID()
    setDraft({ ...draft, beats: [...draft.beats, { id, title: '', development: '', decision: '', constraints: '' }] })
    focusBeat(id)
  }
  return <Modal open onClose={onClose} title="Refine the beat plan" description="Your edit preserves the generated original. A new continuity brief is required before approval." wide><div className="dialog-body form-stack">
    <label className="field"><span>Plan summary</span><textarea maxLength={4000} value={draft.summary} onChange={(event) => setDraft({ ...draft, summary: event.target.value })} /></label>
    {draft.beats.map((beat, index) => <fieldset className="scene-beat-editor form-stack" key={beat.id}><legend>Beat {index + 1}</legend><BeatFields beat={beat} onChange={(change) => update(beat.id, change)} /><ChanceEditor beat={beat} run={run} onChange={(change) => update(beat.id, change)} /><div className="scene-actions"><button className="button quiet" disabled={index === 0} onClick={() => move(index, -1)}>Move beat {index + 1} earlier</button><button className="button quiet" disabled={index === draft.beats.length - 1} onClick={() => move(index, 1)}>Move beat {index + 1} later</button><button className="button quiet" disabled={draft.beats.length === 1} onClick={() => remove(beat.id)}>Remove beat {index + 1}</button></div></fieldset>)}
    <button className="button" disabled={draft.beats.length >= 24} onClick={add}>Add a beat</button><label className="field"><span>Proposed stopping point</span><textarea maxLength={4000} value={draft.ending} onChange={(event) => setDraft({ ...draft, ending: event.target.value })} /></label><ErrorNotice message={action.error} /><button className="button primary" aria-disabled={action.busy} onClick={save}>Save edited plan</button><p className="subtle">Unpublished edits are saved in this browser while you work.</p>
  </div></Modal>
}

function BeatFields({ beat, onChange }: { beat: SceneBeat; onChange: (change: Partial<SceneBeat>) => void }) {
  return <><label className="field"><span>Beat title</span><input id={`scene-beat-title-${beat.id}`} maxLength={200} value={beat.title} onChange={(event) => onChange({ title: event.target.value })} /></label>{([['development', 'Proposed development', 5000], ['decision', 'Decision left open', 3000], ['constraints', 'What to preserve', 3000]] as const).map(([key, label, limit]) => <label className="field" key={key}><span>{label}</span><textarea maxLength={limit} rows={3} value={beat[key]} onChange={(event) => onChange({ [key]: event.target.value })} /></label>)}</>
}
