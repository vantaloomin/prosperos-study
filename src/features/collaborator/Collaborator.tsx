import type { CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MessageSquareText, Plus, X, Move, Maximize2 } from 'lucide-react'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch, Story } from '../../types'
import { SideComposer } from './SideComposer'
import { SideTurnView } from './SideTurnView'
import { activeReply } from './types'
import type { SideThread } from './types'
import type { useCollaboratorLayout, CollaboratorMode } from './useCollaboratorLayout'
import { CollaboratorConnection } from './CollaboratorConnection'
import { defaultSideSettings, type SideSettings } from './sideSettings'

interface Props { story: Story; branch: Branch; onClose: () => void; onInsert: (text: string) => void }

export function Collaborator(props: Props) {
  return <Conversations {...props} />
}

type Layout = ReturnType<typeof useCollaboratorLayout>
export function CollaboratorWindow({ layout, open, ...props }: Props & { layout: Layout; open: boolean }) {
  const { geometry: g, presentation } = layout
  const style: CSSProperties = presentation === 'floating' ? { left: g.left, top: g.top, width: g.width, height: g.height } : { width: g.dockWidth }
  const close = () => { props.onClose(); requestAnimationFrame(focusStoryControl) }
  return <aside hidden={!open} className={`collaborator-dock collaborator-${presentation}`} style={style} aria-label="Collaborator">
    <header><div><MessageSquareText size={17} /><h2>Collaborator</h2></div><button className="icon-button" aria-label="Close collaborator" onClick={close}><X size={18} /></button></header>
    <WindowControls layout={layout} onStory={close} />
    {presentation === 'docked' && <div className="dock-resize-handle" onPointerDown={event => layout.drag(event, 'dock')} aria-hidden="true" />}
    <Collaborator {...props} />
    {presentation === 'floating' && <button className="window-resize-handle icon-button" aria-label="Resize Collaborator; use window controls for keyboard resizing" onPointerDown={event => layout.drag(event, 'resize')} onClick={() => document.querySelector<HTMLDetailsElement>('.window-geometry')?.setAttribute('open', '')}><Maximize2 size={16} /></button>}
  </aside>
}

function focusStoryControl() {
  const controls = Array.from(document.querySelectorAll<HTMLElement>('[aria-label="Open collaborator"]'))
  const target = controls.find(control => control.getClientRects().length && !control.closest('details:not([open])')) ?? document.querySelector<HTMLElement>('.workspace-actions-menu > summary')
  target?.focus({ preventScroll: true })
}

function WindowControls({ layout, onStory }: { layout: Layout; onStory: () => void }) {
  const { geometry, presentation } = layout
  return <div className="collaborator-window-controls"><button className="text-button" onClick={onStory}>Story</button><span aria-current="page">Collaborator</span><label className="field"><span className="sr-only">Collaborator display</span><select aria-label="Collaborator display" value={layout.mode} onChange={event => layout.setMode(event.target.value as CollaboratorMode)}><option value="docked">Docked</option><option value="floating">Floating</option><option value="full">Full workspace</option></select></label>
    {layout.compact && <small>Full workspace fits this window and interface size.</small>}
    {presentation === 'floating' && <button className="text-button window-move-handle" onPointerDown={event => layout.drag(event, 'move')} onClick={() => document.querySelector<HTMLDetailsElement>('.window-geometry')?.setAttribute('open', '')}><Move size={14} />Move window</button>}
    {presentation !== 'full' && <details className="window-geometry"><summary>Window controls</summary><div>{(presentation === 'floating' ? ['left', 'top', 'width', 'height'] as const : ['dockWidth'] as const).map(key => <label className="field" key={key}><span>{key === 'dockWidth' ? 'Dock width' : key} (px)</span><input aria-label={`Collaborator ${key}`} type="number" step="10" value={Math.round(geometry[key])} onChange={event => { if (event.target.value) layout.patch({ [key]: Number(event.target.value) }) }} /></label>)}<button className="text-button" onClick={layout.reset}>Reset position and size</button></div></details>}
  </div>
}

function Conversations(props: Props) {
  const { story, branch } = props
  const query = useQuery({ queryKey: ['side-threads', story.id], queryFn: () => api<SideThread[]>(`/stories/${story.id}/side-conversations`) })
  const [selected, setSelected] = usePersistent(`roleplay:side-thread:${story.id}`, '')
  const [settings, setSettings] = usePersistent<SideSettings>(`roleplay:side-settings:${story.id}`, defaultSideSettings)
  const action = useAction()
  const create = () => action.run(async () => {
    const result = await api<{ id: string }>(`/stories/${story.id}/side-conversations`, { name: `Notes on ${branch.name}` })
    setSelected(result.id)
  })
  return <div className="side-workspace"><CollaboratorConnection storyId={story.id} overrides={settings.profiles} /><div className="side-thread-picker"><select aria-label="Side conversation" value={selected} onChange={(e) => setSelected(e.target.value)}><option value="">Choose a conversation</option>{query.data?.map((thread) => <option key={thread.id} value={thread.id}>{thread.name}</option>)}</select><button className="icon-button" aria-label="New side conversation" onClick={create} disabled={action.busy}><Plus size={17} /></button></div><ErrorNotice message={action.error || query.error?.message} />
    {selected ? <Conversation key={selected} {...props} id={selected} settings={settings} onSettings={setSettings} /> : <div className="side-welcome"><MessageSquareText size={26} /><h3>A little room to think.</h3><p>Explore an idea, review a scene, or improve your next line. This conversation cannot progress your story.</p><button className="button primary" onClick={create} disabled={action.busy}>Start a side conversation</button></div>}
  </div>
}

function Conversation({ id, story, branch, onInsert, onClose, settings, onSettings }: Props & { id: string; settings: SideSettings; onSettings: (value: SideSettings) => void }) {
  const query = useQuery({ queryKey: ['side-thread', id], queryFn: () => api<SideThread>(`/side-conversations/${id}`),
    refetchInterval: (current) => current.state.data?.turns.some((turn) => turn.replies.some(activeReply)) ? 750 : false })
  const working = query.data?.turns.some((turn) => turn.replies.some(activeReply)) ?? false
  return <><div className="side-context-badge"><span>Following {branch.name} · revision {branch.revision}</span><small>Each reply keeps the context it started with.</small></div><ErrorNotice message={query.error?.message} />
    <div className="side-transcript" aria-label="Side conversation messages">{query.data?.turns.map((turn) => <SideTurnView key={turn.id} turn={turn} branch={branch} story={story} onInsert={onInsert} onClose={onClose} />)}</div>
    <SideComposer key={`${id}:${branch.id}`} threadId={id} branch={branch} story={story} working={working} settings={settings} onSettings={onSettings} />
  </>
}
