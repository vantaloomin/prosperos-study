import { BookOpen, Plus, Users } from 'lucide-react'
import { lazy, Suspense, useState, useRef } from 'react'
import type { Branch, Story } from '../../types'
import { Loading } from '../../components/Feedback'
import { ContinuityMemory } from './ContinuityMemory'
import { Modal } from '../../components/Modal'
import { usePersistent } from '../../hooks/usePersistent'

const AttachmentsEditor = lazy(() => import('../library/AttachmentsEditor').then((module) => ({ default: module.AttachmentsEditor })))
const LoreInspection = lazy(() => import('../library/LoreInspection').then((module) => ({ default: module.LoreInspection })))

export function ContextDock({ story, branch, onClose, onReadMessage }: { story: Story; branch: Branch; onClose: () => void; onReadMessage: (messageId: string) => void }) {
  const [tab, setTab] = usePersistent(`roleplay:context-tab:${story.id}`, 'overview')
  const [editing, setEditing] = useState(false)
  const [inspecting, setInspecting] = useState(false)
  const readingSource = useRef(false)
  const readSource = (id: string) => { readingSource.current = true; onReadMessage(id) }
  return <Modal open onClose={onClose} focusOnClose={() => readingSource.current ? document.querySelector<HTMLElement>('[aria-label="Story history"]') : null} title="Context" description="Inspect the story’s overview, memory, cast, and Canon." wide><div className="tabs dock-tabs">{['overview', 'memory', 'cast', 'canon'].map((name) => <button key={name} aria-pressed={tab === name} onClick={() => setTab(name)}>{name}</button>)}</div>
    <div className="dialog-body context-dialog"><ContextContents tab={tab} story={story} branch={branch} onReadMessage={readSource} /><button className="text-button dock-add" onClick={() => setEditing(true)}><Plus size={15} />Manage story library</button>
    {tab === 'canon' && <button className="text-button dock-add" onClick={() => setInspecting(true)}>Inspect Canon on this path</button>}
    </div><footer className="dialog-footer"><span className="subtle">Versioned with your story</span><button className="button" onClick={onClose}>Close context</button></footer>
    {inspecting && <Suspense fallback={<Loading label="Opening Canon decisions…" />}><LoreInspection branchId={branch.id} onClose={() => setInspecting(false)} /></Suspense>}
    {editing && <Suspense fallback={<Loading label="Opening Story library…" />}><AttachmentsEditor story={story} onClose={() => setEditing(false)} /></Suspense>}
  </Modal>
}

function ContextContents({ tab, story, branch, onReadMessage }: { tab: string; story: Story; branch: Branch; onReadMessage: (messageId: string) => void }) {
  if (tab === 'memory') return <ContinuityMemory branch={branch} onReadMessage={onReadMessage} />
  if (tab === 'overview') return <><span className="eyebrow">STORY BRIEF</span><h3>{story.title}</h3><p className="context-prose">{story.premise || 'Add a premise and lasting guidance in Story setup.'}</p><div className="context-section"><span className="eyebrow">YOUR PARTICIPATION</span><p>{String(story.settings.persona || 'You decide what your character does next.')}</p></div><div className="context-section"><span className="eyebrow">CURRENT PATH</span><h4>{branch.name}</h4><p>{branch.messages.filter(message => !message.metadata.removed).length} saved contributions</p></div></>
  const kind = tab === 'cast' ? 'character' : 'lorebook'
  const attached = branch.attachments.filter((item) => (item.kind === 'persona' ? 'character' : item.kind) === kind)
  return <><span className="eyebrow">{{ character: 'PEOPLE IN YOUR WORLD', lorebook: 'WORLD KNOWLEDGE' }[kind]}</span>{attached.map((item) => <details key={item.asset_id} className="context-asset"><summary>{{ character: <Users size={16} />, lorebook: <BookOpen size={16} /> }[kind]}<span>{item.version.name}<small>v{item.version.number}{!item.enabled && ' · inactive'}{item.update_available && ' · update available'}</small></span></summary><p>{item.version.content.text}</p>{kind === 'character' && <p>{[item.version.content.address, item.version.content.pronouns].filter(Boolean).join(' · ')}</p>}</details>)}{!attached.length && <p className="subtle">No {{ character: 'characters', lorebook: 'Canon collections' }[kind]} attached yet.</p>}</>
}
