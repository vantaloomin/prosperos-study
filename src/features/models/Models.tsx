import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Check, Pencil, Plus, PlugZap } from 'lucide-react'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { ProfileEditor } from './ProfileEditor'
import { profileReady } from './profileReadiness'
import { providers } from './types'
import type { ModelProfile, ProfileList } from './types'

export function Models() {
  const query = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles') })
  const [editing, setEditing] = useState<ModelProfile | 'new' | null>(null)
  return <section className="models-section"><div className="section-heading"><div><h2>Your writing partners</h2><p className="subtle">Pick a Primary Writer. Every step inherits it until you choose another profile.</p></div><button className="button primary" onClick={() => setEditing('new')}><Plus size={16} />Add a model</button></div>
    <ErrorNotice message={query.error?.message} />
    {query.isPending && <Loading label="Loading model profiles…" />}
    <div className="model-list">{query.data?.profiles.map((profile) => <ProfileCard key={profile.profile_id} profile={profile} primary={query.data.primary_profile_id === profile.profile_id} onEdit={() => setEditing(profile)} />)}</div>
    {query.data?.profiles.length === 0 && <div className="model-empty"><PlugZap size={28} /><h3>A voice for every kind of story.</h3><p>Add a cloud connection, use your Codex login, or connect a model running on this device. You can keep writing manually while you decide.</p></div>}
    {editing && <ProfileEditor profile={editing === 'new' ? undefined : editing} first={!query.data?.primary_profile_id} onClose={() => setEditing(null)} />}
  </section>
}

function ProfileCard({ profile, primary, onEdit }: { profile: ModelProfile; primary: boolean; onEdit: () => void }) {
  const action = useAction()
  const label = profile.display_name ?? profile.name
  const ready = profileReady(profile.config)
  const [check, setCheck] = useState<{ models: string[]; note?: string } | null>(null)
  const verify = () => action.run(async () => setCheck(await api(`/profiles/${profile.profile_id}/check`, {})))
  const choose = () => action.run(async () => { await api('/profiles/primary', { profile_id: profile.profile_id }, 'PUT') })
  return <article className={`profile-card ${primary ? 'primary-profile' : ''}`}><div className="profile-heading"><div><span className="eyebrow">{providers[profile.config.provider].name}</span><h3>{label}</h3><p className="model-id">{profile.config.model || 'Setup incomplete · choose a model'}</p></div><button className="icon-button" aria-label={`Edit ${label}`} onClick={onEdit}><Pencil size={16} /></button></div>
    <div className="profile-actions"><button className="text-button" onClick={verify} disabled={action.busy}><PlugZap size={15} />{action.busy ? 'Checking…' : 'Check connection'}</button>{primary ? <span className="primary-label"><Check size={14} />Primary Writer</span> : <PrimaryAction ready={ready} busy={action.busy} onChoose={choose} onEdit={onEdit} />}</div>
    <ErrorNotice message={action.error} />{check && <div className="connection-result"><p><Check size={14} />Connection available. No text was generated.</p>{check.note && <small>{check.note}</small>}{check.models.length > 0 && <details><summary>{check.models.length} available model IDs</summary><pre>{check.models.join('\n')}</pre></details>}</div>}
  </article>
}

function PrimaryAction({ ready, busy, onChoose, onEdit }: { ready: boolean; busy: boolean; onChoose: () => void; onEdit: () => void }) {
  return <button className="text-button" onClick={ready ? onChoose : onEdit} disabled={busy}>{ready ? 'Use as Primary Writer' : 'Finish setup'}</button>
}
