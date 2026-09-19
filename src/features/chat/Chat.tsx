import { useQuery } from '@tanstack/react-query'
import { lazy, Suspense, useRef, useState, useLayoutEffect } from 'react'
import { api } from '../../api'
import { Empty, ErrorNotice, Loading } from '../../components/Feedback'
import type { Branch, Selection, Story } from '../../types'
import { BranchMap } from './BranchMap'
import { Composer } from './Composer'
import { MessageCard } from './MessageCard'
import { ContextDock } from './ContextDock'
import { StoryDetails } from '../stories/StoryDetails'
import { GenerationControls } from '../generation/GenerationControls'
import { WritingRecovery, WritingSurface } from '../generation/WritingSurface'
import { CollaboratorWindow } from '../collaborator/Collaborator'
import { useCollaboratorLayout } from '../collaborator/useCollaboratorLayout'
import type { DraftTransfer } from './Composer'
import { loadBranch, useBranchReadiness } from './navigationTiming'
import { TranscriptPosition } from './readingPosition'
import { PassageNavigation, type PassageReader } from './passageNavigation'
import { passagePosition } from './transcriptWindow'
import { useImperativeHandle, type Ref } from 'react'
import { Modal } from '../../components/Modal'
import { ChatHeading } from './ChatHeading'
import { PendingBranch } from './PendingBranch'
import { messageLabels, storyMode, type StoryMode } from '../stories/storyMode'
const WindowedTranscript = lazy(() => import('./WindowedTranscript').then((module) => ({ default: module.WindowedTranscript })))

const Randomness = lazy(() => import('../mechanics/Randomness').then((module) => ({ default: module.Randomness })))
const Workflow = lazy(() => import('../workflow/Workflow').then((module) => ({ default: module.Workflow })))
const ManuscriptWorkspace = lazy(() => import('../manuscript/ManuscriptWorkspace').then(module => ({ default: module.ManuscriptWorkspace })))

interface Props { storyId: string; branchId: string; onBranch: (id: string) => void; onOpen: (selection: Selection) => void }

export function Chat({ storyId, branchId, onBranch, onOpen }: Props) {
  const storyQuery = useQuery({ queryKey: ['story', storyId], queryFn: () => api<Story>(`/stories/${storyId}`) })
  const resolved = branchId || storyQuery.data?.branches[0]?.id || ''
  const branchQuery = useQuery({ queryKey: ['branch', resolved], queryFn: () => loadBranch(resolved), enabled: !!resolved })
  if (storyQuery.error) return <main className="page"><ErrorNotice message={storyQuery.error.message} /><button className="button" onClick={() => void storyQuery.refetch()}>Try again</button></main>
  if (!storyQuery.data) return <Loading />
  if (branchQuery.error || !branchQuery.data) return <PendingBranch story={storyQuery.data} branchId={resolved} error={branchQuery.error?.message} onRetry={() => void branchQuery.refetch()} onBranch={onBranch} />
  return <ChatWorkspace key={storyId} story={storyQuery.data} branch={branchQuery.data} onBranch={onBranch} onOpen={onOpen} />
}

function ChatWorkspace({ story, branch, onBranch, onOpen }: { story: Story; branch: Branch; onBranch: (id: string) => void; onOpen: (selection: Selection) => void }) {
  const mode = storyMode(story.settings)
  const [reading] = useState(() => new PassageNavigation())
  const workspace = useRef<HTMLDivElement>(null)
  useBranchReadiness(branch, workspace)
  const [context, setContext] = useState(false)
  const [tools, setTools] = useState(false)
  const [map, setMap] = useState(false)
  const [mapOpenedAt, setMapOpenedAt] = useState(0)
  const openMap = () => { setMapOpenedAt(performance.now()); setMap(true) }
  const [details, setDetails] = useState(false)
  const [side, setSide] = useState(false)
  const layout = useCollaboratorLayout()
  const fullscreen = [side, layout.presentation === 'full'].every(Boolean)
  const [randomness, setRandomness] = useState(false)
  const [workflow, setWorkflow] = useState(false)
  const [manuscript, setManuscript] = useState(false)
  const [transfer, setTransfer] = useState<DraftTransfer | null>(null)
  const toggleContext = () => { setContext(!context); setSide(false); setTools(false) }
  const toggleSide = () => { setSide(!side); setContext(false); setTools(false) }
  const toggleTools = () => { setTools(!tools); setContext(false); setSide(false) }
  const withDock = [side && layout.presentation === 'docked', tools].some(Boolean)
  const readMessage = (messageId: string) => {
    if (reading.request(branch.id, messageId)) setContext(false)
  }
  const closeTools = () => { setTools(false); focusTools(workspace.current) }
  if (manuscript) return <Suspense fallback={<Loading label="Opening the book…" />}><ManuscriptWorkspace story={story} branchId={branch.id} onClose={() => setManuscript(false)} /></Suspense>
  return <div ref={workspace} data-active-branch={branch.id} className={`chat-workspace ${withDock ? 'with-context' : ''}`}><GenerationControls key={`generation:${branch.id}`} branch={branch} onBranch={onBranch} onReadMessage={readMessage} open={tools} onClose={closeTools} onOpen={() => setTools(true)}><main className="chat-main" inert={fullscreen} aria-hidden={fullscreen}>
    <ChatHeading story={story} branchName={branch.name} context={context} side={side} tools={tools} onTools={toggleTools} onMap={openMap} onWorkflow={() => setWorkflow(true)} onManuscript={() => setManuscript(true)} onDetails={() => setDetails(true)} onContext={toggleContext} onSide={toggleSide} />
    {branch.messages.length >= 200 ? <Suspense fallback={<Loading label="Opening your reading position…" />}><WindowedTranscript reader={reading.connect} key={`window:${branch.id}`} branch={branch} mode={mode} onBranch={onBranch} /></Suspense> : <Transcript reader={reading.connect} key={`transcript:${branch.id}`} branch={branch} mode={mode} onBranch={onBranch} />}
    <WritingRecovery /><Composer key={`composer:${branch.id}`} branch={branch} mode={mode} transfer={transfer} onTransferred={() => setTransfer(null)} onRandomness={() => setRandomness(true)} />
  </main></GenerationControls>{context && <ContextDock onReadMessage={readMessage} story={story} branch={branch} onClose={() => setContext(false)} />}
    <CollaboratorWindow open={side} layout={layout} story={story} branch={branch} onClose={() => setSide(false)} onInsert={(text) => { setTransfer({ id: crypto.randomUUID(), branchId: branch.id, text }); requestAnimationFrame(() => workspace.current?.querySelector<HTMLTextAreaElement>('[aria-label="Story message"]')?.focus()) }} />
    {map && <BranchMap branches={story.branches} selected={branch.id} onSelect={onBranch} onClose={() => setMap(false)} openedAt={mapOpenedAt} />}
    {details && <StoryDetails story={story} branchId={branch.id} onOpen={onOpen} onClose={() => setDetails(false)} />}
    {randomness && <Modal open title="A little room for chance" description="Shape the unexpected. A reply is not automatically a beat, and a roll is only a proposal until its draft is accepted." onClose={() => setRandomness(false)} wide><Suspense fallback={<Loading label="Opening your tables…" />}><Randomness branch={branch} onBranch={onBranch} /></Suspense></Modal>}
    {workflow && <Modal open title="Story workflow" description="Plan a scene, invite independent readers, and choose the right partner for each step." onClose={() => setWorkflow(false)} wide><Suspense fallback={<Loading label="Opening the workflow…" />}><Workflow key={branch.id} branch={branch} onBranch={(id) => { setWorkflow(false); onBranch(id) }} /></Suspense></Modal>}
  </div>
}

function focusTools(workspace: HTMLElement | null) {
  const controls = Array.from(workspace?.querySelectorAll<HTMLElement>('[aria-label="Writing tools"]') ?? [])
  const target = controls.find(control => control.getClientRects().length && !control.closest('details:not([open])')) ?? workspace?.querySelector<HTMLElement>('.workspace-actions-menu > summary')
  target?.focus({ preventScroll: true })
}

function Transcript({ branch, mode, onBranch, reader }: { branch: Branch; mode: StoryMode; onBranch: (id: string) => void; reader: Ref<PassageReader> }) {
  const labels = messageLabels(mode)
  const container = useRef<HTMLDivElement>(null)
  const position = useRef<TranscriptPosition | null>(null)
  useLayoutEffect(() => {
    const element = container.current
    if (!element) return
    const controller = new TranscriptPosition(element, branch.id)
    position.current = controller
    return () => { controller.dispose(); position.current = null }
  }, [branch.id])
  useLayoutEffect(() => {
    position.current?.refresh()
  }, [branch.messages.length])
  useImperativeHandle(reader, () => ({ branchId: branch.id, show: (messageId) => {
    if (!branch.messages.some((message) => message.id === messageId)) return false
    position.current?.seek(passagePosition(messageId))
    container.current?.focus({ preventScroll: true })
    return true
  } }), [branch.id, branch.messages])
  return <div className="transcript" data-transcript-ready="true" ref={container} tabIndex={0} role="region" aria-label="Story history">
    {branch.messages.length === 0 ? <><Empty title="The next sentence is yours."><p>Write a passage, set the scene, or leave a note for your writer.<br />Every possibility has a place here.</p><span className="empty-rule" /></Empty><div className="reading-column"><WritingSurface after={null} /></div></> : <div className="reading-column"><div className="chapter-mark"><span />A beginning, and what followed<span /></div>{branch.messages.map((message) => <div key={message.id}><MessageCard message={message} label={labels[message.role]} branch={branch} onBranch={onBranch} /><WritingSurface after={message.id} /></div>)}<WritingSurface after={null} /><div className="end-mark">· · ·</div></div>}
  </div>
}
