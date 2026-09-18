import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { ProfileList } from '../models/types'

export function LibraryModels() {
  const defaults = useQuery({ queryKey: ['authoring-defaults'], queryFn: () => api<Record<string, string>>('/authoring/defaults') })
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles') })
  const action = useAction()
  const save = (step: string, value: string) => action.run(async () => { await api('/authoring/defaults', { step, profile_id: value || null }, 'PUT') })
  const roles = [{ key: 'library-assist', label: 'Library assistant' }, { key: 'scribe', label: 'Library canon aids (Scribe)' }]
  return <details className="advanced-settings"><summary>Models for Library work</summary><p className="subtle">Workspace defaults for Library work. Retained task assignments can be changed in the Library assistant’s model controls.</p><ErrorNotice message={action.error || defaults.error?.message || profiles.error?.message} />{roles.map(role => <label className="field" key={role.key}><span>{role.label}</span><select value={defaults.data?.[role.key] ?? ''} disabled={action.busy} onChange={event => void save(role.key, event.target.value)}><option value="">Workspace Primary Writer</option>{profiles.data?.profiles.map(profile => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)}</select></label>)}</details>
}
