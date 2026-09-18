import { useState } from 'react'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { ModelProfile } from '../models/types'
import type { Routing, WorkflowStep } from './types'
import { sameAssignments } from './routingState'

type RoutingProps = { storyId: string; data: Routing; profiles: ModelProfile[]; onPrompt: (key: string) => void }

export function RoutingEditor(props: RoutingProps) {
  const [saved, setSaved] = useState(false)
  return <><RoutingForm key={props.storyId} {...props} onSaved={() => setSaved(true)} onDirty={() => setSaved(false)} /><p role="status" className="subtle">{saved && 'Step assignments saved. Future requests will use these models.'}</p></>
}

function RoutingForm({ storyId, data, profiles, onPrompt, onSaved, onDirty }: RoutingProps & { onSaved: () => void; onDirty: () => void }) {
  const [revision, setRevision] = useState(data.story_revision)
  const [baseline, setBaseline] = useState(data)
  const [draft, setDraft] = usePersistent(`roleplay:routing:${storyId}:${revision}`, { primary: data.primary_profile_id ?? '', steps: data.step_profiles })
  const action = useAction()
  const primary = draft.primary || data.workspace_primary_id
  const primaryName = profiles.find((profile) => profile.profile_id === primary)?.name ?? 'No Primary Writer selected'
  const changeStep = (key: string, value: string) => {
    onDirty()
    const steps = { ...draft.steps }
    if (value) steps[key] = value
    else delete steps[key]
    setDraft({ ...draft, steps })
  }
  const save = () => action.run(async () => {
    const current = await api<Routing>(`/stories/${storyId}/workflow`)
    if (!sameAssignments(current, baseline)) throw new Error('Step assignments changed in another view. Reopen Models by step to review them; your draft is preserved.')
    const result = await api<Routing>(`/stories/${storyId}/workflow`, { expected_revision: current.story_revision, primary_profile_id: draft.primary || null, step_profiles: draft.steps }, 'PUT')
    localStorage.removeItem(`roleplay:routing:${storyId}:${revision}`)
    setRevision(result.story_revision)
    setBaseline(result)
    onSaved()
  })
  return <div className="form-stack"><div><h3>A partner for each step</h3><p className="subtle">One Primary Writer is enough to begin. Overrides stay assigned when the Primary Writer changes. Past requests retain their original versions.</p></div>
    <label className="field"><span>Primary Writer for this story</span><select disabled={action.busy} value={draft.primary} onChange={(event) => { onDirty(); setDraft({ ...draft, primary: event.target.value }) }}><option value="">Use workspace Primary Writer</option>{profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)}</select><small>Effective default: {primaryName}</small></label>
    <div className="routing-steps">{data.steps.map((step) => <div key={step.key}><RoutingRow step={step} value={draft.steps[step.key] ?? ''} primaryName={primaryName} profiles={profiles} busy={action.busy} onChange={(value) => changeStep(step.key, value)} onPrompt={() => onPrompt(step.key)} />{!!step.tasks?.length && <details className="advanced-settings"><summary>{step.name} task assignments</summary><p className="subtle">An empty task assignment inherits this role. Retained overrides stay explicit.</p>{step.tasks.map(task => <label className="field" key={task.key}><span>{task.label}{task.historical && ' · historical task'}{!task.enabled && ' · disabled in Prompts'}</span><select value={draft.steps[task.key] ?? ''} disabled={action.busy || task.historical} onChange={event => changeStep(task.key, event.target.value)}><option value="">Use {step.name} model</option>{profiles.map(profile => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)}</select></label>)}</details>}</div>)}</div>
    <p className="subtle">Changes affect future requests in this story. Existing prepared beats may need an explicit reroll after a configuration change.</p><ErrorNotice message={action.error} /><button className="button primary" aria-disabled={action.busy} onClick={save}>Save step assignments</button>
  </div>
}

function RoutingRow({ step, value, primaryName, profiles, busy, onChange, onPrompt }: { step: WorkflowStep; value: string; primaryName: string; profiles: ModelProfile[]; busy: boolean; onChange: (value: string) => void; onPrompt: () => void }) {
  return <div className="routing-row"><div><strong>{step.name}</strong><small>{value ? 'Assigned profile' : `Inherits ${primaryName}`}</small></div><label className="field"><span className="sr-only">Model for {step.name}</span><select aria-label={`Model for ${step.name}`} disabled={busy} value={value} onChange={(event) => onChange(event.target.value)}><option value="">Primary Writer</option>{profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)}</select></label><button className="text-button" onClick={onPrompt} aria-label={`Edit ${step.name} prompt`}>Edit prompt</button></div>
}
