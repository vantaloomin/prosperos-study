import { BookOpen, Plus, Users, X } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import type { Branch, Story } from '../../types'
import { Loading } from '../../components/Feedback'
import { ContinuityMemory } from './ContinuityMemory'

const AttachmentsEditor = lazy(() => import('../library/AttachmentsEditor').then((module) => ({ default: module.AttachmentsEditor })))
const LoreInspection = lazy(() => import('../library/LoreInspection').then((module) => ({ default: module.LoreInspection })))

export function ContextDock({ story, branch, onClose }: { story: Story; branch: Branch; onClose: () => void }) {
  const [tab, setTab] = useState('scene')
  const [editing, setEditing] = useState(false)
  const [inspecting, setInspecting] = useState(false)
  return <aside className="context-dock" aria-label="Story context"><header><h2>Context</h2><button className="icon-button" aria-label="Close context" onClick={onClose}><X size={18} /></button></header><div className="tabs dock-tabs">{['scene', 'memory', 'cast', 'canon'].map((name) => <button key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>{name}</button>)}</div>
    <div className="dock-content"><ContextContents tab={tab} story={story} branch={branch} /><button className="text-button dock-add" onClick={() => setEditing(true)}><Plus size={15} />Manage story library</button></div>
    {tab === 'canon' && <button className="text-button dock-add" onClick={() => setInspecting(true)}>Inspect Canon on this path</button>}
    <footer className="dock-footer"><span className="status-dot" />Versioned with your story</footer>
    {inspecting && <Suspense fallback={<Loading label="Opening Canon decisions…" />}><LoreInspection branchId={branch.id} onClose={() => setInspecting(false)} /></Suspense>}
    {editing && <Suspense fallback={<Loading label="Opening Story library…" />}><AttachmentsEditor story={story} onClose={() => setEditing(false)} /></Suspense>}
  </aside>
}

function ContextContents({ tab, story, branch }: { tab: string; story: Story; branch: Branch }) {
  if (tab === 'memory') return <ContinuityMemory branch={branch} />
  if (tab === 'scene') return <><span className="eyebrow">THE SITUATION</span><h3>{story.title}</h3><p className="context-prose">{story.premise || 'Give this story a little context in Story details.'}</p><div className="context-section"><span className="eyebrow">YOUR PARTICIPATION</span><p>{String(story.settings.persona || 'You decide what your character does next.')}</p></div><div className="context-section"><span className="eyebrow">CURRENT PATH</span><h4>{branch.name}</h4><p>{branch.messages.length} saved contributions</p></div></>
  const kind = tab === 'cast' ? 'character' : 'lorebook'
  const attached = branch.attachments.filter((item) => (item.kind === 'persona' ? 'character' : item.kind) === kind)
  return <><span className="eyebrow">{{ character: 'PEOPLE IN YOUR WORLD', lorebook: 'WORLD KNOWLEDGE' }[kind]}</span>{attached.map((item) => <details key={item.asset_id} className="context-asset"><summary>{{ character: <Users size={16} />, lorebook: <BookOpen size={16} /> }[kind]}<span>{item.version.name}<small>v{item.version.number}{!item.enabled && ' · inactive'}{item.update_available && ' · update available'}</small></span></summary><p>{item.version.content.text}</p>{kind === 'character' && <p>{[item.version.content.address, item.version.content.pronouns].filter(Boolean).join(' · ')}</p>}</details>)}{!attached.length && <p className="subtle">No {{ character: 'characters', lorebook: 'Canon collections' }[kind]} attached yet.</p>}</>
}
