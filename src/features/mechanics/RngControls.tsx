import { useState } from 'react'
import { api } from '../../api'
import { Field } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch } from '../../types'
import type { MechanicsContext, RngSettings } from './types'
import { TableExclusions } from './TableExclusions'

const mechanisms = [['narrative_push', 'Narrative Push', 'Develop an interaction already in progress.'], ['encounter', 'Encounter', 'Discover what is present during exploration or a transition.'], ['handling', 'Handling an attempted action', 'Resolve a specifically chosen action; never choose for the player.']] as const
const components = [['proficiency', 'Domain proficiency die'], ['fracture', 'Fracture die'], ['preparation', 'Preparation die'], ['subresults', 'Handling outcome shape'], ['carriers', 'Outcome carrier'], ['textures', 'Optional texture draws'], ['pressure_cap', 'Pressure cap after two strong results'], ['domain_progression', 'Domain changes on exceptional results']] as const

export function RngControls({ branch, data, onSaved }: { branch: Branch; data: MechanicsContext; onSaved: () => void }) {
  const [settings, setSettings] = usePersistent(`roleplay:rng-draft:${branch.story_id}:${data.story_revision}`, data.settings)
  const [latest, setLatest] = useState(false)
  const action = useAction()
  const pending = latest || JSON.stringify(settings) !== JSON.stringify(data.settings)
  const patch = (change: Partial<RngSettings>) => setSettings({ ...settings, ...change })
  const save = () => action.run(async () => {
    await api(`/stories/${branch.story_id}/randomness`, { expected_revision: data.story_revision, settings, use_latest_tables: latest }, 'PUT')
    onSaved()
  })
  return <div className="form-stack"><p role="status" className="subtle">{action.busy ? 'Saving randomness settings…' : pending ? 'Unsaved changes — the workspace still uses the saved setting.' : 'Saved randomness settings'}</p><label className="mechanic-master check-row"><input type="checkbox" checked={settings.enabled} onChange={(e) => patch({ enabled: e.target.checked })} /><span>Automatic randomness: {settings.enabled ? 'On ✓' : 'Off'}<small>Off by default. Explicit Roll now and isolated table previews remain available.</small></span></label>
    <label className="check-row"><input type="checkbox" checked={!!settings.automatic_assessment} disabled={!settings.enabled} onChange={(e) => patch({ automatic_assessment: e.target.checked })} /><span>Assess meaningful beats during ordinary chat<small>Before writing, an optional model step checks completion and player agency. It inherits Primary Writer; customize its model and prompt in Workflow. Adds one model request unless you explicitly compare assessments.</small></span></label>
    <div className="mechanic-options">{mechanisms.map(([key, label, hint]) => <label className="check-row" key={key}><input type="checkbox" checked={settings[key]} onChange={(e) => patch({ [key]: e.target.checked })} /><span>{label}<small>{hint}</small></span></label>)}</div>
    <section className="form-stack"><div><h3>Give the story breathing room</h3><p className="subtle">One shared cooldown across both event families. Check only when a meaningful beat is complete.</p></div><div className="preset-buttons">{[['Quiet', 10, 4], ['Balanced', 15, 3], ['Lively', 25, 2]].map(([label, chance, cooldown]) => <button className="button" key={label} onClick={() => patch({ chance: Number(chance), cooldown: Number(cooldown) })}>{label}</button>)}</div><div className="mechanic-fields"><Field label="Event chance (%)" type="number" min={0} max={100} value={settings.chance} onChange={(e) => patch({ chance: Number(e.target.value) })} /><Field label="Eligible beats of breathing room" type="number" min={0} max={100} value={settings.cooldown} onChange={(e) => patch({ cooldown: Number(e.target.value) })} /><Field label="Major disruptions per scene" type="number" min={0} max={100} value={settings.major_limit} onChange={(e) => patch({ major_limit: Number(e.target.value) })} /></div><p className="subtle">New scenes begin with the selected breathing room. No-event and suppressed results still start the cooldown. A missed check does not.</p></section>
    <details className="mechanics-advanced"><summary>Components, optional tables & changed odds</summary><div className="form-stack"><div className="mechanic-options">{components.map(([key, label]) => <label className="check-row" key={key}><input type="checkbox" checked={settings[key]} onChange={(e) => patch({ [key]: e.target.checked })} />{label}</label>)}</div><ExtraControls settings={settings} data={data} onChange={patch} /><TableExclusions tables={data.tables} settings={settings} onChange={patch} /></div></details>
    <label className="check-row"><input type="checkbox" checked={latest} onChange={(e) => setLatest(e.target.checked)} /><span>Adopt the latest library table versions for future beats<small>Previously prepared beats keep their original table versions and settings.</small></span></label>
    <ErrorNotice message={action.error} /><div className="mechanics-footer"><p className="subtle">Changes apply to future opportunities in this story. Existing prepared beats may become stale.</p><button className="button primary" onClick={save} disabled={action.busy}>Save randomness settings</button></div>
  </div>
}

function ExtraControls({ settings, data, onChange }: { settings: RngSettings; data: MechanicsContext; onChange: (change: Partial<RngSettings>) => void }) {
  const extras = data.tables.filter((table) => ['extra', 'texture'].includes(table.definition.purpose))
  const toggle = (key: string) => onChange({ enabled_extras: settings.enabled_extras.includes(key) ? settings.enabled_extras.filter((item) => item !== key) : [...settings.enabled_extras, key] })
  const texture = (key: string, value: string) => { const next = { ...settings.texture_tables }; if (value) next[key] = value; else delete next[key]; onChange({ texture_tables: next }) }
  return <><div><h3>Optional inspiration & resolution</h3><p className="subtle">Enabled tables can be requested when preparing a beat. They never roll on every reply.</p><div className="mechanic-options">{extras.map((table) => <label className="check-row" key={table.table_id}><input type="checkbox" checked={settings.enabled_extras.includes(table.table_id)} onChange={() => toggle(table.table_id)} />{table.definition.name}</label>)}</div></div><div><h3>Story textures</h3><p className="subtle">Optional tables for handling outcomes. Unassigned textures make no draws.</p><div className="mechanic-fields">{[['small-wrongs', 'Small wrongs'], ['small-rights', 'Small rights'], ['interruptions', 'Timing interruptions'], ['who-shows-up', 'Who shows up']].map(([key, label]) => <label className="field" key={key}><span>{label}</span><select value={settings.texture_tables[key] ?? ''} onChange={(e) => texture(key, e.target.value)}><option value="">No texture table</option>{extras.map((table) => <option key={table.table_id} value={table.table_id}>{table.definition.name}</option>)}</select></label>)}</div></div></>
}
