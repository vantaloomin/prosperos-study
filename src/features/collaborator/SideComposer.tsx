import { useQuery } from '@tanstack/react-query'
import { ArrowUp } from 'lucide-react'
import { readyProfiles } from '../models/profileReadiness'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch, Story } from '../../types'
import type { ProfileList } from '../models/types'
import type { SideSettings as Settings } from './sideSettings'

export function SideComposer({ threadId, branch, story, working, settings, onSettings }: { threadId: string; branch: Branch; story: Story; working: boolean; settings: Settings; onSettings: (settings: Settings) => void }) {
  const [text, setText] = usePersistent(`roleplay:side-draft:${threadId}`, '')
  const action = useAction()
  const ask = () => action.run(async () => {
    await api(`/side-conversations/${threadId}/questions`, { operation_id: operationId(), branch_id: branch.id,
      expected_revision: branch.revision, question: text, profile_ids: settings.profiles,
      compare_branch_ids: settings.paths, disclosure: settings.disclosure, max_reads: settings.reads })
    setText('')
  })
  const invalidComparison = settings.compare && settings.profiles.length < 2
  return <form className="side-composer" onSubmit={(e) => { e.preventDefault(); void ask() }}><ErrorNotice message={action.error} />
    <textarea aria-label="Message to collaborator" placeholder="Think out loud. Nothing here advances the story." rows={3} value={text} onChange={(e) => setText(e.target.value)} />
    <div className="side-send"><span className="subtle">Separate from the narrative</span><button className="send-button" type="submit" aria-label="Ask collaborator" disabled={!text.trim() || working || action.busy || invalidComparison}><ArrowUp size={18} /></button></div>
    <SideOptions branch={branch} story={story} settings={settings} onChange={onSettings} />
  </form>
}

const toggle = (items: string[], id: string) => items.includes(id) ? items.filter((item) => item !== id) : [...items, id]

function SideOptions({ branch, story, settings, onChange }: { branch: Branch; story: Story; settings: Settings; onChange: (settings: Settings) => void }) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const patch = (next: Partial<Settings>) => onChange({ ...settings, ...next })
  return <details className="side-options"><summary>Model, sources & disclosure</summary><ErrorNotice message={profiles.error?.message} />
    <label className="field"><span>Request profile override</span><select aria-label="Collaborator request profile override" disabled={settings.compare} value={settings.profiles[0] ?? ''} onChange={(e) => patch({ profiles: e.target.value ? [e.target.value] : [] })}><option value="">Use connection shown above</option>{profiles.data?.profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)}</select></label>
    <label className="check-row"><input type="checkbox" checked={settings.compare} onChange={(e) => patch({ compare: e.target.checked, profiles: [] })} />Compare replies from several profiles</label>
    {settings.compare && <div className="side-profile-choices">{profiles.data?.profiles.map((profile) => <label key={profile.profile_id} className="check-row"><input type="checkbox" checked={settings.profiles.includes(profile.profile_id)} onChange={() => patch({ profiles: toggle(settings.profiles, profile.profile_id) })} />{profile.display_name ?? profile.name}</label>)}<small>Choose 2–4 profiles. Select one reply for the following discussion.</small></div>}
    <label className="field"><span>Disclosure</span><select aria-label="Collaborator disclosure" value={settings.disclosure} onChange={(e) => patch({ disclosure: e.target.value })}><option value="spoiler-conscious">Spoiler-conscious presentation</option><option value="full-disclosure">Full disclosure, including hidden lore</option></select></label>
    <details><summary>Include other paths explicitly</summary>{story.branches.filter((item) => item.id !== branch.id).map((item) => <label className="check-row" key={item.id}><input type="checkbox" checked={settings.paths.includes(item.id)} onChange={() => patch({ paths: toggle(settings.paths, item.id) })} />{item.name}</label>)}</details>
    <label className="field"><span>Additional source-reading passes</span><input aria-label="Source-reading passes" type="number" min={0} max={4} value={settings.reads} onChange={(e) => patch({ reads: Number(e.target.value) })} /></label><p className="subtle">At most {settings.reads + 1} model requests per profile. Long story mode uses paged archive search and exact passage reads. Other stories use the complete source index. Private background is excluded from Long story discovery unless you choose full disclosure. Coverage appears beside each reply.</p>
  </details>
}
