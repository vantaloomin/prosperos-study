import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { ModelProfile } from '../models/types'
import { PromptEditor, type Prompt } from '../prompts/Prompts'
import type { AuthoringStep } from './types'

export function ModelChoices({ profiles, selected, compare, onMode, onChange }: { profiles: ModelProfile[]; selected: string[]; compare: boolean; onMode: (value: boolean) => void; onChange: (values: string[]) => void }) {
  const toggle = (id: string) => onChange(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id])
  return <><label className="check-row"><input type="checkbox" checked={compare} onChange={(event) => onMode(event.target.checked)} />Compare several model profiles</label>
    {compare ? <div className="asset-choices">{profiles.map((profile) => <label className="check-row" key={profile.profile_id}><input type="checkbox" checked={selected.includes(profile.profile_id)} onChange={() => toggle(profile.profile_id)} />{profile.display_name ?? profile.name}</label>)}<p className="subtle">Choose 2–4 profiles. All alternatives use the same draft and instructions.</p></div>
      : <label className="field"><span>Model for this request</span><select value={selected[0] ?? ''} onChange={(event) => onChange(event.target.value ? [event.target.value] : [])}><option value="">Use this step’s saved default</option><ProfileOptions profiles={profiles} /></select></label>}
  </>
}

function ProfileOptions({ profiles }: { profiles: ModelProfile[] }) {
  return profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)
}

export function AuthoringDefaults({ step, profiles, onChange }: { step: AuthoringStep; profiles: ModelProfile[]; onChange: () => void }) {
  const defaults = useQuery({ queryKey: ['authoring-defaults'], queryFn: () => api<Record<string, string>>('/authoring/defaults') })
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const action = useAction()
  const save = (id: string) => action.run(async () => { await api('/authoring/defaults', { step, profile_id: id || null }, 'PUT'); onChange() })
  const edit = () => action.run(async () => { const prompts = await api<Prompt[]>('/prompts'); setPrompt(prompts.find((item) => item.key === (step === 'authoring-enrich' ? 'scribe' : 'library-assist')) ?? null) })
  return <details className="advanced-settings"><summary>Instructions & saved model for this action</summary><div className="form-stack authoring-history">
    <p className="subtle">These Library settings apply across the workspace. Actions inherit the Library role model unless you choose a task override here. Request selections override it once.</p>
    {defaults.data && <label className="field"><span>Saved model for this action</span><select value={defaults.data[step] ?? ''} disabled={action.busy} onChange={(event) => save(event.target.value)}><option value="">Use Library role model</option><ProfileOptions profiles={profiles} /></select></label>}
    <button className="text-button" onClick={edit} aria-disabled={action.busy}>Edit action instructions</button><ErrorNotice message={action.error || defaults.error?.message} />
    {prompt && <PromptEditor prompt={prompt} onClose={() => { setPrompt(null); onChange() }} />}
  </div></details>
}
