import { useState } from 'react'
import { api, operationId } from '../../api'
import { Field, TextField } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch } from '../../types'
import type { Attempt, Beat, MechanicsContext } from './types'

const emptyBeat: Beat = { label: '', completed: true, waiting_for_player: false, protected: false, resolves_event: false, new_scene: false, family: 'narrative-push', attempt: null, extras: [] }
const emptyAttempt: Attempt = { action: '', actor: '', domain: '', level: 0, fractured: false, prepared: false }

export function PrepareBeat({ branch, data, onBranch, onInspect }: { branch: Branch; data: MechanicsContext; onBranch: (id: string) => void; onInspect: (id: string) => void }) {
  const [beat, setBeat] = usePersistent(`roleplay:beat-draft:${branch.id}:${branch.head_id}`, emptyBeat)
  const [manual, setManual] = useState(false)
  const action = useAction()
  const patch = (change: Partial<Beat>) => setBeat({ ...beat, ...change })
  const prepare = () => action.run(async () => {
    const result = await api<{ id: string; branch_id: string }>(`/branches/${branch.id}/opportunities`, { operation_id: operationId(), expected_revision: branch.revision, beat, manual })
    onBranch(result.branch_id)
    onInspect(result.id)
  })
  if (data.pending) return <div className="form-stack"><div className="prepared-card"><span className="eyebrow">Prepared for this point</span><h3>{data.pending.label}</h3><p className="subtle">Future prose alternatives reuse this beat. It has not advanced the branch.</p>{data.pending.stale && <p className="subtle">Story settings changed after preparation. Inspect this beat to reroll on a new branch, or write without it.</p>}</div><button className="button" onClick={() => onInspect(data.pending!.id)}>Inspect prepared beat</button><StateSummary data={data} /></div>
  return <div className="form-stack"><StateSummary data={data} /><Field label="What meaningful beat has completed?" value={beat.label} maxLength={500} onChange={(e) => patch({ label: e.target.value })} placeholder="The introductions are over; everyone has taken a seat." />
    <label className="field"><span>Event family</span><select value={beat.family} onChange={(e) => patch({ family: e.target.value as Beat['family'] })}><option value="narrative-push">Narrative Push · develop this interaction</option><option value="encounter">Encounter · explore or transition</option><option value="none">No event · handling or optional tables only</option></select></label>
    <div className="mechanic-options">{[['completed', 'This meaningful beat is complete'], ['waiting_for_player', 'The player still has a choice or action to finish'], ['protected', 'Keep this moment uninterrupted'], ['resolves_event', 'The earlier generated event is resolved'], ['new_scene', 'This begins a new scene']].map(([key, label]) => <label className="check-row" key={key}><input type="checkbox" checked={Boolean(beat[key as keyof Beat])} onChange={(e) => patch({ [key]: e.target.checked })} />{label}</label>)}</div>
    <details className="mechanics-advanced"><summary>Attempted action & optional inspiration</summary><div className="form-stack"><label className="check-row"><input type="checkbox" checked={!!beat.attempt} onChange={(e) => patch({ attempt: e.target.checked ? emptyAttempt : null })} />Resolve a specifically chosen action</label>{beat.attempt && <AttemptFields value={beat.attempt} onChange={(attempt) => patch({ attempt })} />}<ExtraRequests data={data} beat={beat} onChange={patch} /></div></details>
    <label className="check-row"><input type="checkbox" checked={manual} onChange={(e) => setManual(e.target.checked)} /><span>Roll now, as an explicit one-time request<small>Bypasses the automatic master, selected-mechanic toggles and cadence. Eligibility, component toggles, table exclusions and scene limits still apply.</small></span></label>
    {!data.enabled && !manual && <p className="subtle">Automatic randomness is off. Save enabled settings or choose the explicit one-time request.</p>}<ErrorNotice message={action.error} /><div className="mechanics-footer"><p className="subtle">No model call. No story changes until you accept the resulting narration.</p><button className="button primary" onClick={prepare} disabled={action.busy || !beat.label.trim() || (!data.enabled && !manual)}>{manual ? 'Roll now & prepare' : 'Prepare this beat'}</button></div>
  </div>
}

function StateSummary({ data }: { data: MechanicsContext }) {
  return <p className="subtle">Accepted state: scene {data.state.scene}, {data.state.beat} completed beats. Breathing room remaining: {data.state.cooldown ?? data.settings.cooldown} eligible beats.{data.state.unresolved_event && ' A generated event is still unresolved.'}</p>
}

export function AttemptFields({ value, onChange }: { value: Attempt; onChange: (value: Attempt) => void }) {
  const patch = (change: Partial<Attempt>) => onChange({ ...value, ...change })
  return <div className="form-stack"><TextField label="Action already chosen by the character" value={value.action} onChange={(e) => patch({ action: e.target.value })} rows={2} /><div className="mechanic-fields"><Field label="Acting character" value={value.actor} onChange={(e) => patch({ actor: e.target.value })} /><Field label="Matched domain (optional)" value={value.domain} onChange={(e) => patch({ domain: e.target.value })} /><Field label="Initial domain level (−5 to +5)" type="number" min={-5} max={5} value={value.level} onChange={(e) => patch({ level: Number(e.target.value) })} hint="A previously accepted domain change takes precedence." /></div><label className="check-row"><input type="checkbox" checked={value.fractured} onChange={(e) => patch({ fractured: e.target.checked })} />A relevant fracture applies</label><label className="check-row"><input type="checkbox" checked={value.prepared} onChange={(e) => patch({ prepared: e.target.checked })} />Preparation is already established on the page</label></div>
}

function ExtraRequests({ data, beat, onChange }: { data: MechanicsContext; beat: Beat; onChange: (change: Partial<Beat>) => void }) {
  const extras = data.tables.filter((table) => ['extra', 'texture'].includes(table.definition.purpose))
  const toggle = (id: string) => onChange({ extras: beat.extras.includes(id) ? beat.extras.filter((item) => item !== id) : [...beat.extras, id] })
  return <div><h3>Additional prompts</h3><p className="subtle">Choose only what this beat needs. Disabled sources are skipped unless you explicitly choose Roll now.</p><div className="mechanic-options">{extras.map((table) => <label className="check-row" key={table.table_id}><input type="checkbox" checked={beat.extras.includes(table.table_id)} onChange={() => toggle(table.table_id)} />{table.definition.name}</label>)}</div></div>
}
