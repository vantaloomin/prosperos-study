import { lazy, Suspense, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import type { Branch, Story } from '../../types'
import type { ProfileList } from '../models/types'
import { MemoryPreferences } from '../stories/MemoryPreferences'
import { useAction } from '../../hooks/useAction'
import './memory-readiness.css'

const ProfileEditor = lazy(() => import('../models/ProfileEditor').then(module => ({ default: module.ProfileEditor })))
const RelationshipPanel = lazy(() => import('../storyMemory/RelationshipPanel').then(module => ({ default: module.RelationshipPanel })))

interface ReadinessItem { key: string; label: string; state: string; detail: string; action: string; profile_id: string | null }
interface Readiness { writer: { profile_id: string; name: string } | null; writer_reason: string; items: ReadinessItem[] }
interface Props { branch: Branch; profileId: string; characterLens: boolean }

export function MemoryReadiness({ branch, profileId, characterLens }: Props) {
  const [action, setAction] = useState<ReadinessItem | null>(null)
  const query = useQuery({ queryKey: ['memory-readiness', branch.id, branch.revision, profileId, characterLens],
    queryFn: () => api<Readiness>(`/branches/${branch.id}/memory-readiness?${new URLSearchParams({ profile_id: profileId, character_lens: String(characterLens) })}`), refetchInterval: 30000 })
  const data = query.data
  return <><details className="memory-readiness request-details"><summary>{readinessHeading(data, query.isError)}</summary>
    <p className="subtle">For new writing with the current settings. This check makes no model calls. Draft receipts show what was actually supplied.</p>
    {query.isPending && <p role="status">Reading saved settings…</p>}
    <ErrorNotice message={query.error?.message} />
    {query.isError ? <button className="text-button" onClick={() => void query.refetch()}>Refresh readiness</button> : <ReadinessRows data={data} onAction={setAction} />}
  </details>{action && <Suspense fallback={<p role="status">Opening memory settings…</p>}><ReadinessAction key={action.key} branch={branch} action={action} writerId={data?.writer?.profile_id ?? profileId} onClose={() => setAction(null)} /></Suspense>}</>
}

function readinessHeading(data: Readiness | undefined, failed: boolean) {
  if (failed) return 'Memory readiness · unavailable'
  return data?.writer ? `Memory readiness · ${data.writer.name}` : 'Memory readiness'
}

function ReadinessRows({ data, onAction }: { data?: Readiness; onAction: (row: ReadinessItem) => void }) {
  if (!data) return null
  return <>{data.writer_reason && <p role="status">{data.writer_reason}</p>}
    <ul>{data.items.map(row => <li key={row.key}><div><strong>{row.label}</strong><span>{row.state}</span></div><p>{row.detail}</p>
      <button className="text-button" onClick={() => onAction(row)}>{actionLabel(row.action)}</button></li>)}</ul>
    <p className="subtle">Automatic summary maintenance and wording cleanup have separate controls. Readiness does not measure continuity accuracy.</p>
  </>
}

function actionLabel(action: string) {
  if (action === 'relationships') return 'Open relationship links'
  if (action === 'background') return 'Open preparation writer'
  return action === 'writer' ? 'Open writer profile' : 'Open memory preferences'
}

function ReadinessAction({ branch, action, writerId, onClose }: { branch: Branch; action: ReadinessItem; writerId: string; onClose: () => void }) {
  if (action.action === 'relationships') return <Modal open wide title="Relationship links" description="Prepare and inspect tentative links to exact accepted passages." onClose={onClose}><div className="dialog-body"><RelationshipPanel branch={branch} /></div></Modal>
  if (action.action === 'writer' || action.action === 'background') return <ReadinessProfile profileId={action.profile_id ?? writerId} onClose={onClose} />
  return <ReadinessPreferences storyId={branch.story_id} onClose={onClose} />
}

function ReadinessProfile({ profileId, onClose }: { profileId: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles') })
  if (!query.data || query.isError) return <Modal open title="Writer profile" description="Open the saved connection used by this memory feature." onClose={onClose}><div className="dialog-body"><p>Loading saved profiles…</p><ErrorNotice message={query.error?.message} /></div></Modal>
  const profile = query.data.profiles.find(row => row.profile_id === profileId)
  if (profileId && !profile) return <Modal open title="Writer profile unavailable" description="The saved selection is no longer available." onClose={onClose}><div className="dialog-body">Select an available writer in Writing tools.</div></Modal>
  return <ProfileEditor profile={profile} first={!query.data.primary_profile_id} onClose={onClose} />
}

function ReadinessPreferences({ storyId, onClose }: { storyId: string; onClose: () => void }) {
  const query = useQuery({ queryKey: ['story', storyId], queryFn: () => api<Story>(`/stories/${storyId}`) })
  return <Modal open title="Story memory preferences" description="Changes apply to new requests. Saved drafts retain their original inputs." onClose={onClose}>
    {query.data ? <PreferenceForm story={query.data} onClose={onClose} /> : <div className="dialog-body"><p>Loading preferences…</p><ErrorNotice message={query.error?.message} /></div>}
  </Modal>
}

function PreferenceForm({ story, onClose }: { story: Story; onClose: () => void }) {
  const [saved] = useState(story)
  const [settings, setSettings] = useState(story.settings)
  const action = useAction()
  const save = () => action.run(async () => {
    await api(`/stories/${saved.id}`, { title: saved.title, premise: saved.premise, archived: saved.archived, settings, expected_revision: saved.revision }, 'PUT')
    onClose()
  })
  return <><div className="dialog-body form-stack"><MemoryPreferences value={settings} onChange={setSettings} /><ErrorNotice message={action.error} /></div><footer className="dialog-footer"><button className="button primary" disabled={action.busy} onClick={save}>Save memory preferences</button></footer></>
}
