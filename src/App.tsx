import { lazy, Suspense, useEffect, useRef, useState, type CSSProperties } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { MotionConfig } from 'motion/react'
import { BookOpen, Menu, Feather, Plus, Settings2 } from 'lucide-react'
import { api } from './api'
import { Modal } from './components/Modal'
import { StudyMark } from './components/StudyMark'
import { Tooltips } from './components/Tooltips'
import { ErrorNotice, Loading } from './components/Feedback'
import { usePersistent } from './hooks/usePersistent'
import { useMediaQuery } from './hooks/useMediaQuery'
import type { Selection, StorySummary } from './types'
import { StoryList } from './features/stories/StoryList'
import { Chat } from './features/chat/Chat'
import { defaultAppearance, appearanceStyles, type Appearance } from './features/settings/appearance'
import { beginBranchNavigation } from './features/chat/navigationTiming'
import { acknowledgeReturn, isCompanionWindow, returnSelection } from './features/collaborator/popOutWindow'
import { companionOpenEvent } from './features/collaborator/companionFocus'
import { useStartWritingFocus } from './features/stories/useStartWritingFocus'

type Page = 'chat' | 'library' | 'settings'
const Library = lazy(() => import('./features/library/Library').then((module) => ({ default: module.Library })))
const Settings = lazy(() => import('./features/settings/Settings').then((module) => ({ default: module.Settings })))
const NewStory = lazy(() => import('./features/stories/NewStory').then((module) => ({ default: module.NewStory })))
const CompanionPopOut = lazy(() => import('./features/collaborator/CompanionPopOut').then(module => ({ default: module.CompanionPopOut })))
const companionWindow = isCompanionWindow()

export default function App() {
  const cache = useQueryClient()
  const [page, setPage] = useState<Page>('chat')
  const [selection, setSelection] = usePersistent<Selection>('roleplay:selection', { storyId: '', branchId: '' })
  const [appearance, setAppearance] = usePersistent<Appearance>('roleplay:appearance', defaultAppearance)
  useEffect(() => {
    document.documentElement.dataset.theme = appearance.theme
    document.documentElement.dataset.reduceMotion = String(appearance.reducedMotion)
    const values = Object.entries(appearanceStyles(appearance))
    for (const [name, value] of values) document.documentElement.style.setProperty(name === 'colorScheme' ? 'color-scheme' : name, value)
    return () => { for (const [name] of values) document.documentElement.style.removeProperty(name === 'colorScheme' ? 'color-scheme' : name) }
  }, [appearance])
  const [creating, setCreating] = useState(false)
  const startWriting = useStartWritingFocus(selection, page === 'chat', creating)
  const [mobileStories, setMobileStories] = useState(!selection.storyId)
  const [companionReturn, setCompanionReturn] = useState(() => new URLSearchParams(window.location.search).has('companion_return') ? 1 : 0)
  useEffect(() => {
    if (companionWindow) return
    const receive = (event: MessageEvent) => {
      const next = returnSelection(event)
      if (!next) return
      setSelection(next); setPage('chat'); setMobileStories(false); setCompanionReturn(value => value + 1)
      acknowledgeReturn(event)
    }
    window.addEventListener('message', receive)
    const open = (event: Event) => {
      const next = (event as CustomEvent<Selection>).detail
      setSelection(next); setPage('chat'); setMobileStories(false); setCompanionReturn(value => value + 1)
    }
    window.addEventListener(companionOpenEvent, open)
    return () => { window.removeEventListener('message', receive); window.removeEventListener(companionOpenEvent, open) }
  }, [setSelection])
  const narrow = useMediaQuery('(max-width: 900px)')
  const showMobileStories = [mobileStories, narrow, page === 'chat'].every(Boolean)
  const stories = useQuery({ queryKey: ['stories'], queryFn: () => api<StorySummary[]>('/stories'), enabled: !companionWindow })
  const select = (storyId: string) => { setSelection({ storyId, branchId: '' }); setPage('chat'); setMobileStories(false) }
  const branch = (branchId: string) => {
    beginBranchNavigation(branchId, !!cache.getQueryData(['branch', branchId]))
    setSelection({ ...selection, branchId })
  }
  return <MotionConfig reducedMotion={appearance.reducedMotion ? 'always' : 'user'}><div className={`app-shell${companionWindow ? ' companion-app' : ''}`} data-theme={appearance.theme} data-reduce-motion={appearance.reducedMotion} style={appearanceStyles(appearance) as CSSProperties}>
    {companionWindow ? <Suspense fallback={<Loading label="Opening Companion Pop Out…" />}><CompanionPopOut /></Suspense> : <>
    <Rail page={page} onPage={setPage} onStories={() => { setPage('chat'); setMobileStories(!mobileStories) }} />
    <Workspace companionReturn={companionReturn} page={page} storiesOpen={mobileStories && !narrow} onCollapse={() => setMobileStories(false)} stories={stories.data ?? []} pending={stories.isPending} error={stories.error?.message} selection={selection} appearance={appearance} onAppearance={setAppearance} onSelect={select} onBranch={branch} onOpen={(next) => { beginBranchNavigation(next.branchId, !!cache.getQueryData(['branch', next.branchId])); setSelection(next); setPage('chat'); setMobileStories(false) }} onNew={() => setCreating(true)} />
    {creating && <Suspense fallback={<Loading label="Opening Story setup…" />}><NewStory onClose={() => setCreating(false)} onCreated={(next) => { setSelection(next); startWriting(next); setPage('chat'); setMobileStories(false) }} /></Suspense>}
    {showMobileStories && <MobileStories stories={stories.data ?? []} selected={selection.storyId} onClose={() => setMobileStories(false)} onSelect={select} onNew={() => { setMobileStories(false); setCreating(true) }} />}
    </>}
    <Tooltips />
  </div></MotionConfig>
}

function MobileStories({ stories, selected, onSelect, onNew, onClose }: { stories: StorySummary[]; selected: string; onSelect: (id: string) => void; onNew: () => void; onClose: () => void }) {
  const starting = useRef(false)
  const start = () => { starting.current = true; onNew() }
  return <Modal open onClose={onClose} focusOnClose={() => starting.current ? document.querySelector<HTMLElement>('.setup-step-heading') : null} title="Your stories" description="Return to a familiar place, or start somewhere new."><StoryList stories={stories} selected={selected} onSelect={onSelect} onNew={start} /><footer className="dialog-footer"><button className="button primary" onClick={start}><Plus size={16} />New story</button></footer></Modal>
}

function Rail({ page, onPage, onStories }: { page: Page; onPage: (page: Page) => void; onStories: () => void }) {
  return <nav className="app-rail" aria-label="Workspace navigation"><a className="study-home" href="#" onClick={(e) => { e.preventDefault(); onPage('chat') }} aria-label="Prospero’s Study home" title="Prospero’s Study"><StudyMark /></a><button aria-label="Show stories" onClick={onStories}><Menu /><span>Stories</span></button>
    <div className="rail-links"><button aria-label="Write" aria-current={page === 'chat' ? 'page' : undefined} onClick={() => onPage('chat')}><Feather /><span>Write</span></button><button aria-label="Library" aria-current={page === 'library' ? 'page' : undefined} onClick={() => onPage('library')}><BookOpen /><span>Library</span></button></div>
    <button className="rail-settings" aria-label="Settings" aria-current={page === 'settings' ? 'page' : undefined} onClick={() => onPage('settings')}><Settings2 /><span>Settings</span></button>
  </nav>
}

interface WorkspaceProps {
  companionReturn: number
  storiesOpen: boolean; onCollapse: () => void
  page: Page; stories: StorySummary[]; pending: boolean; error?: string; selection: Selection
  appearance: Appearance; onAppearance: (next: Appearance) => void
  onSelect: (id: string) => void; onBranch: (id: string) => void; onNew: () => void
  onOpen: (selection: Selection) => void
}

function Workspace(props: WorkspaceProps) {
  if (props.page === 'library') return <Suspense fallback={<Loading label="Opening the Library…" />}><Library /></Suspense>
  if (props.page === 'settings') return <Suspense fallback={<Loading label="Opening settings…" />}><Settings appearance={props.appearance} onChange={props.onAppearance} selection={props.selection} onOpen={props.onOpen} /></Suspense>
  return <>{props.storiesOpen && <div className="desktop-stories"><button className="text-button collapse-stories" onClick={props.onCollapse}>Collapse stories</button><StoryList stories={props.stories} selected={props.selection.storyId} onSelect={props.onSelect} onNew={props.onNew} /></div>}<StorySurface {...props} /></>
}

function StorySurface({ pending, error, selection, onBranch, onNew, onOpen, companionReturn }: WorkspaceProps) {
  if (pending) return <Loading />
  if (error) return <main className="page"><ErrorNotice message={error} /><p className="subtle">Check that the local application server is running.</p></main>
  if (selection.storyId) return <Chat storyId={selection.storyId} branchId={selection.branchId} onBranch={onBranch} onOpen={onOpen} companionReturn={companionReturn} />
  return <main className="welcome" aria-labelledby="welcome-title">
    <div className="welcome-top"><span className="eyebrow">YOUR WRITING ROOM</span><span className="subtle">Make yourself at home.</span></div>
    <section className="welcome-body">
      <StudyMark size={96} />
      <span className="eyebrow">A little room for possibility</span>
      <h1 id="welcome-title" className="welcome-name">Prospero’s Study</h1>
      <p className="welcome-lede">Write a scene. Follow a character.<br />See where the next page takes you.</p>
      <button className="button primary" onClick={onNew}><Plus size={16} />Begin a story</button>
      <p className="welcome-note">No perfect first line required.</p>
    </section>
    <p className="welcome-footnote">Writing <span aria-hidden="true">·</span> Worldbuilding <span aria-hidden="true">·</span> Roleplay</p>
  </main>
}
