import { lazy, Suspense, useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MessageSquareText, Plus, X, Move, Maximize2 } from 'lucide-react'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch, Story } from '../../types'
import { SideComposer } from './SideComposer'
import type { PrepareCompanion } from './SideComposer'
import { PopOutControl } from './PopOutControl'
import './popOut.css'
import { SideTurnView } from './SideTurnView'
import { activeReply } from './types'
import type { ConversationLocation, SideThread } from './types'
import type { useCollaboratorLayout, CollaboratorMode } from './useCollaboratorLayout'
import { CollaboratorConnection } from './CollaboratorConnection'
import { defaultSideSettings, type SideSettings } from './sideSettings'
import { CompanionTarget } from './CompanionTarget'
import { companionFocusKey, followCompanionFocus, showCompanion } from './companionFocus'
import type { CompanionFocus } from './contextTypes'
import { popupTransfer } from './popupTransfer'

interface Props { story: Story; branch: Branch; onClose: () => void; onInsert: (text: string) => void | Promise<void>; prepare?: PrepareCompanion }
const ConversationManager = lazy(() => import('./ConversationManager').then(module => ({ default: module.ConversationManager })))

export function Collaborator(props: Props) {
  const [focus] = usePersistent<CompanionFocus>(companionFocusKey, null, true)
  if (focus && (focus.storyId !== props.story.id || focus.branchId !== props.branch.id)) return <FocusedCompanion {...props} focus={focus} />
  return <Conversations {...props} />
}

function FocusedCompanion({ focus, ...props }: Props & { focus: NonNullable<CompanionFocus> }) {
  const story = useQuery({ queryKey: ['story', focus.storyId], queryFn: () => api<Story>(`/stories/${focus.storyId}`), refetchInterval: 2500 })
  const branch = useQuery({ queryKey: ['branch', focus.branchId], queryFn: () => api<Branch>(`/branches/${focus.branchId}`), refetchInterval: 2500 })
  const transfer = useMemo(() => popupTransfer({ kind: 'document', story_id: focus.storyId, branch_id: focus.branchId, purpose: 'composer' }), [focus.storyId, focus.branchId])
  if (!story.data || !branch.data) return <><ErrorNotice message={story.error?.message || branch.error?.message} /><Loading label="Opening the pinned Companion Story…" /><button type="button" className="button" onClick={followCompanionFocus}>Return to the active workspace</button></>
  if (branch.data.story_id !== story.data.id) return <ErrorNotice message="The pinned telling belongs to another Story. Reopen its source context." />
  return <Conversations {...props} story={story.data} branch={branch.data} onInsert={async text => { await transfer(text); showCompanion(focus) }} />
}

type Layout = ReturnType<typeof useCollaboratorLayout>
export function CollaboratorWindow({ layout, open, ...props }: Props & { layout: Layout; open: boolean }) {
  const prepare = useRef<(() => Promise<void>) | null>(null)
  const { geometry: g, presentation } = layout
  const style: CSSProperties = presentation === 'floating' ? { left: g.left, top: g.top, width: g.width, height: g.height } : { width: g.dockWidth }
  const close = () => { props.onClose(); requestAnimationFrame(focusStoryControl) }
  return <aside hidden={!open} className={`collaborator-dock collaborator-${presentation}`} style={style} aria-label="Collaborator">
    <header><div><MessageSquareText size={17} /><h2>Collaborator</h2></div><button className="icon-button" aria-label="Close collaborator" onClick={close}><X size={18} /></button></header>
    <WindowControls layout={layout} onStory={close} />
    <PopOutControl selection={{ storyId: props.story.id, branchId: props.branch.id }} prepare={prepare} />
    {presentation === 'docked' && <div className="dock-resize-handle" onPointerDown={event => layout.drag(event, 'dock')} aria-hidden="true" />}
    {open && <Collaborator {...props} prepare={prepare} />}
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
  const query = useQuery({ queryKey: ['side-threads', story.id], queryFn: () => api<SideThread[]>(`/stories/${story.id}/side-conversations?include_archived=true`), refetchInterval: 2500 })
  useQuery({ queryKey: ['story', story.id], queryFn: () => api<Story>(`/stories/${story.id}`), refetchInterval: 2500 })
  useQuery({ queryKey: ['branch', branch.id], queryFn: () => api<Branch>(`/branches/${branch.id}`), refetchInterval: 2500 })
  const [manage, setManage] = useState(false)
  const [location, setLocation] = useState<ConversationLocation | null>(null)
  const [selected, setSelected] = usePersistent(`roleplay:side-thread:${story.id}`, '', true)
  const [settings, setSettings] = usePersistent<SideSettings>(`roleplay:side-settings:${story.id}`, defaultSideSettings, true)
  const action = useAction()
  const create = () => action.run(async () => {
    const result = await api<{ id: string }>(`/stories/${story.id}/side-conversations`, { name: `Notes on ${branch.name}`.slice(0, 120) })
    setLocation(null)
    setSelected(result.id)
  })
  return <div className="side-workspace"><CollaboratorConnection storyId={story.id} overrides={settings.profiles} /><div className="side-thread-picker"><select aria-label="Side conversation" value={selected} onChange={(e) => { setSelected(e.target.value); setLocation(null) }}><option value="">Choose a conversation</option>{query.data?.filter(thread => !thread.curation?.archived || thread.id === selected).map((thread) => <option key={thread.id} value={thread.id}>{thread.name}{thread.curation?.archived ? ' · archived' : ''}</option>)}</select><button className="icon-button" aria-label="New side conversation" onClick={create} disabled={action.busy}><Plus size={17} /></button></div><button className="text-button side-manage-conversations" onClick={() => setManage(true)}>Find & organize conversations</button><ErrorNotice message={action.error || query.error?.message} />
    {manage && <Suspense fallback={<p className="subtle">Opening conversations…</p>}><ConversationManager storyId={story.id} selected={selected} onClose={() => setManage(false)} onChoose={(id, location) => { setSelected(id); setLocation(location) }} /></Suspense>}
    {selected ? <Conversation key={selected} {...props} id={selected} settings={settings} onSettings={setSettings} location={location} /> : <div className="side-welcome"><MessageSquareText size={26} /><h3>A little room to think.</h3><p>Explore an idea, review a scene, or improve your next line. This conversation cannot progress your story.</p><button className="button primary" onClick={create} disabled={action.busy}>Start a side conversation</button></div>}
  </div>
}

function Conversation({ id, story, branch, onInsert, onClose, settings, onSettings, location, prepare }: Props & { id: string; settings: SideSettings; onSettings: (value: SideSettings) => void; location: ConversationLocation | null }) {
  const query = useQuery({ queryKey: ['side-thread', id], queryFn: () => api<SideThread>(`/side-conversations/${id}`),
    refetchInterval: (current) => current.state.data?.turns.some((turn) => turn.replies.some(activeReply)) ? 750 : 2500 })
  const working = query.data?.turns.some((turn) => turn.replies.some(activeReply)) ?? false
  const transcript = useRef<HTMLDivElement>(null)
  const delivered = useRef<ConversationLocation | null>(null)
  useLayoutEffect(() => {
    if (!location || delivered.current === location) return
    const target = transcript.current?.querySelector<HTMLElement>(`[data-side-turn="${CSS.escape(location.turnId)}"]`)
    if (!target) return
    const frame = requestAnimationFrame(() => { target.scrollIntoView({ block: 'start' }); target.focus({ preventScroll: true }); delivered.current = location })
    return () => cancelAnimationFrame(frame)
  }, [location, query.data])
  if (query.data && query.data.story_id !== story.id) return <ErrorNotice message="This conversation belongs to another Story. Choose a conversation in this Story or create one above." />
  return <><CompanionTarget threadId={id} branch={branch} /><ErrorNotice message={query.error?.message} />
    <div ref={transcript} className="side-transcript" aria-label="Side conversation messages">{query.data?.turns.map((turn) => <SideTurnView key={`${turn.id}:${location?.turnId === turn.id ? location.replyId : ''}`} focusReplyId={location?.turnId === turn.id ? location.replyId : null} turn={turn} branch={branch} story={story} onInsert={onInsert} onClose={onClose} />)}</div>
    <SideComposer key={id} threadId={id} branch={branch} story={story} working={working} settings={settings} onSettings={onSettings} prepare={prepare} />
  </>
}
