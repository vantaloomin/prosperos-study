import { useState } from 'react'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { ProfileEditor } from '../models/ProfileEditor'
import { providers, type ModelProfile, type ProfileList } from '../models/types'

export function SetupWriter({ value, profiles, onChange }: { value: string; profiles: ProfileList; onChange: (id: string) => void }) {
  const [editing, setEditing] = useState<ModelProfile | 'new' | null>(null)
  const selected = profiles.profiles.find((item) => item.profile_id === (value || profiles.primary_profile_id))
  return <div className="form-stack"><p className="subtle">Every writing and review step starts with your Primary Writer. Change individual steps or compare several profiles later in Workflow.</p>
    <label className="field"><span>Writing profile</span><select value={value} onChange={(event) => onChange(event.target.value)}><option value="">{profiles.primary_profile_id ? 'Use the workspace Primary Writer' : 'Choose later · write manually'}</option>{profiles.profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.name} · {providers[profile.config.provider].name}</option>)}</select></label>
    <div className="row-actions"><button className="button" onClick={() => setEditing('new')}>Add a writing partner</button>{selected && <button className="text-button" onClick={() => setEditing(selected)}>Edit selected profile</button>}</div>
    {selected ? <div className="setup-callout"><strong>{selected.name}</strong><p className="subtle">{providers[selected.config.provider].name} · {selected.config.model}</p><ConnectionCheck key={selected.id} profile={selected} /></div> : <p className="subtle">You can begin without a model. Add a cloud connection, Codex login, or a local server whenever you are ready.</p>}
    <p className="subtle">Stories are stored on this device. Generating with a cloud service sends the selected context to that service. Local profiles use the server address you configure.</p>
    {editing && <ProfileEditor profile={editing === 'new' ? undefined : editing} first={profiles.profiles.length === 0} onSaved={(profile) => { if (profile.config.model.trim()) onChange(profile.profile_id) }} onClose={() => setEditing(null)} />}
  </div>
}

interface Check { available: boolean; models: string[]; note?: string }
function ConnectionCheck({ profile }: { profile: ModelProfile }) {
  const action = useAction()
  const [result, setResult] = useState<Check | null>(null)
  const check = () => action.run(async () => { setResult(null); setResult(await api<Check>(`/profiles/${profile.profile_id}/check`, {})) })
  return <div className="form-stack setup-check"><button className="button" aria-disabled={action.busy} onClick={check}>{action.busy ? 'Checking connection…' : 'Check connection'}</button>{result && <p role="status" className="subtle">{connectionMessage(result, profile.config.model)}</p>}<ErrorNotice message={action.error} /><small>Checks the service or CLI login. No passage is generated. A successful check does not guarantee a later generation will succeed.</small></div>
}

function connectionMessage(result: Check, model: string): string {
  if (!result.available) return 'The service is unavailable. You can save this profile and reconnect later.'
  if (result.note) return result.note
  if (result.models.includes(model)) return 'Connection reached. Your selected model appears in the service’s model list.'
  return 'Connection reached, but the selected model was not listed. Check its ID and account access before generating.'
}
