import { lazy, Suspense, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { readyProfiles } from '../models/profileReadiness'
import type { ProfileList, ModelProfile } from '../models/types'
import type { Routing } from '../workflow/types'
const Models = lazy(() => import('../models/Models').then(module => ({ default: module.Models })))

export function CollaboratorConnection({ storyId, overrides }: { storyId: string; overrides: string[] }) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const routing = useQuery({ queryKey: ['routing', storyId], queryFn: () => api<Routing>(`/stories/${storyId}/workflow`) })
  const [changing, setChanging] = useState(false)
  const [managing, setManaging] = useState(false)
  const action = useAction()
  const { assigned, names, provenance } = resolvedConnection(profiles.data, routing.data, overrides)
  const change = (id: string) => action.run(async () => {
    const current = await api<Routing>(`/stories/${storyId}/workflow`)
    if ((current.step_profiles.collaborator ?? '') !== assigned) throw new Error('The Collaborator assignment changed in another view. Refresh before choosing again.')
    const steps = { ...current.step_profiles }
    if (id) steps.collaborator = id
    else delete steps.collaborator
    await api(`/stories/${storyId}/workflow`, { expected_revision: current.story_revision, primary_profile_id: current.primary_profile_id, step_profiles: steps }, 'PUT')
    setChanging(false)
  })
  return <div className="collaborator-connection"><strong>{names.length ? names.map(profile => `${profile!.name} · ${profile!.config.model}`).join(' / ') : 'Choose a connection'}</strong><small>{provenance}</small><button className="text-button" onClick={() => setChanging(!changing)}>Change connection</button><button className="text-button" onClick={() => setManaging(true)}>Manage connections</button>
    {changing && <label className="field"><span>Collaborator for this story</span><select aria-label="Collaborator for this story" disabled={action.busy} value={assigned} onChange={event => void change(event.target.value)}><option value="">Inherit Primary Writer</option>{profiles.data?.profiles.map(profile => <option key={profile.profile_id} value={profile.profile_id}>{profile.name} · {profile.config.model}</option>)}</select><small>Saved for future questions. An explicit request override in the options below takes precedence.</small></label>}
    <ErrorNotice message={action.error || routing.error?.message || profiles.error?.message} />
    {managing && <Modal open onClose={() => setManaging(false)} title="Collaborator connections" description="Save or edit connections, then return to this conversation." wide><div className="dialog-body"><Suspense fallback={<Loading />}><Models /></Suspense></div><footer className="dialog-footer"><button className="button" onClick={() => setManaging(false)}>Return to Collaborator</button></footer></Modal>}
  </div>
}

function resolvedConnection(profiles: ProfileList | undefined, data: Routing | undefined, overrides: string[]) {
  const assigned = data?.step_profiles.collaborator ?? ''
  const ids = overrides.length ? overrides : [assigned || data?.effective_primary_id]
  const available = profiles?.profiles ?? []
  const names = ids.map(id => available.find(profile => profile.profile_id === id)).filter((profile): profile is ModelProfile => !!profile)
  const provenance = overrides.length ? 'Request override' : assigned ? 'Saved Collaborator assignment' : 'Primary Writer'
  return { assigned, names, provenance }
}
