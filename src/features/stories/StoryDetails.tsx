import { lazy, Suspense, useState } from 'react'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { Field, TextField } from '../../components/Fields'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Selection, Story } from '../../types'

const StoryAgents = lazy(() => import('../prompts/AgentTemplates').then(module => ({ default: module.StoryAgents })))
const StoryWritingPreferences = lazy(() => import('../writing/StoryWritingPreferences').then(module => ({ default: module.StoryWritingPreferences })))
const TextEditWindow = lazy(() => import('../textEdits/TextEditWindow').then(module => ({ default: module.TextEditWindow })))
const TextEditHistory = lazy(() => import('../textEdits/TextEditHistory').then(module => ({ default: module.TextEditHistory })))

const TranscriptExport = lazy(() => import('../export/TranscriptExport').then((module) => ({ default: module.TranscriptExport })))
const Archives = lazy(() => import('../export/Archives').then((module) => ({ default: module.Archives })))
const StoryPreferences = lazy(() => import('./StoryPreferences').then((module) => ({ default: module.StoryPreferences })))
const StoryImportSources = lazy(() => import('../migration/StoryImportSources').then(module => ({ default: module.StoryImportSources })))

export function StoryDetails({ story, branchId, onClose, onOpen }: { story: Story; branchId: string; onClose: () => void; onOpen: (selection: Selection) => void }) {
  const [revision] = useState(story.revision)
  const [title, setTitle] = useState(story.title)
  const [premise, setPremise] = useState(story.premise)
  const [archived, setArchived] = useState(story.archived)
  const [settings, setSettings] = useState(story.settings)
  const [preferences, setPreferences] = useState(false)
  const [agents, setAgents] = useState(false)
  const [writingDefaults, setWritingDefaults] = useState(false)
  const [textView, setTextView] = useState<'brief' | 'history' | null>(null)
  const [exporting, setExporting] = useState(false)
  const [archiving, setArchiving] = useState(false)
  const action = useAction()
  const save = () => action.run(async () => {
    await api(`/stories/${story.id}`, { title, premise, archived, settings, expected_revision: revision }, 'PUT')
    onClose()
  })
  const dirty = setupChanged(story, { title, premise, archived, settings })
  if (textView) return <StoryTextChanges view={textView} storyId={story.id} onClose={onClose} onOpen={onOpen} />
  if (agents) return <Modal open wide title="Story agents" description="Choose the writing partners and guidance for this Story." onClose={onClose}><div className="dialog-body"><Suspense fallback={<Loading />}><StoryAgents storyId={story.id} /></Suspense></div></Modal>
  if (writingDefaults) return <Modal open title="Story writing defaults" description="Choose saved styles and recipes for this Story." onClose={onClose}><div className="dialog-body"><Suspense fallback={<Loading />}><StoryWritingPreferences storyId={story.id} onSaved={onClose} /></Suspense></div></Modal>
  return <><Modal open onClose={onClose} title="Story setup" description="A title, a direction, and room to grow."><div className="dialog-body form-stack"><Field label="Title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} /><TextField label="Story brief" rows={8} value={premise} onChange={(e) => setPremise(e.target.value)} hint="Premise, tone, and standing guidance for this story. Author’s notes belong to a path; Scene goal directs one planned scene. Changes affect future writing." /><details className="advanced-settings" onToggle={(event) => setPreferences(event.currentTarget.open)}><summary>Writing preferences</summary>{preferences && <Suspense fallback={<Loading label="Opening preferences…" />}><StoryPreferences value={settings} onChange={setSettings} /></Suspense>}</details><label className="check-row"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />Archive this story</label><button className="button" disabled={dirty} onClick={() => setTextView('brief')}>Review a Story brief change</button><button className="button" disabled={dirty} onClick={() => setTextView('history')}>Text change history</button><button className="button" disabled={dirty} onClick={() => setAgents(true)}>Agents</button><button className="button" disabled={dirty} onClick={() => setWritingDefaults(true)}>Style & recipe defaults</button>{dirty && <p className="subtle">Save Story setup before opening text changes, agents, or writing defaults.</p>}<Suspense fallback={<Loading />}><StoryImportSources storyId={story.id} /></Suspense><button className="button" onClick={() => setExporting(true)}>Export transcript</button><button className="button" onClick={() => setArchiving(true)}>Private archive & recovery</button><ErrorNotice message={action.error} /></div><footer className="dialog-footer"><span className="subtle">Archived stories can be restored.</span><button className="button primary" disabled={action.busy || !title.trim()} onClick={save}>Save story setup</button></footer></Modal>
    {exporting && <Suspense fallback={<Loading label="Opening export…" />}><TranscriptExport story={story} initialBranchId={branchId} onClose={() => setExporting(false)} /></Suspense>}
    {archiving && <Modal open onClose={() => setArchiving(false)} title="A copy of this world" description="Preserve the saved paths and the details that made them possible." wide><div className="dialog-body"><Suspense fallback={<Loading label="Opening archives…" />}><Archives story={story} selection={{ storyId: story.id, branchId }} onOpen={onOpen} /></Suspense></div></Modal>}
  </>
}

function setupChanged(story: Story, draft: Pick<Story, 'title' | 'premise' | 'archived' | 'settings'>) {
  return draft.title !== story.title || draft.premise !== story.premise || draft.archived !== story.archived || JSON.stringify(draft.settings) !== JSON.stringify(story.settings)
}

function StoryTextChanges({ view, storyId, onClose, onOpen }: { view: 'brief' | 'history'; storyId: string; onClose: () => void; onOpen: (selection: Selection) => void }) {
  const onBranch = (branchId: string) => onOpen({ storyId, branchId })
  return <Suspense fallback={<Loading label="Opening text changes…" />}>{view === 'brief' ? <TextEditWindow initial={{ target: { kind: 'story-brief', story_id: storyId } }} onClose={onClose} onBranch={onBranch} focusOnClose={textChangesFocus} /> : <TextEditHistory storyId={storyId} onClose={onClose} onBranch={onBranch} focusOnClose={textChangesFocus} />}</Suspense>
}

function textChangesFocus() {
  return Array.from(document.querySelectorAll<HTMLElement>('[aria-label="Story setup"], [aria-label="Workspace tools"]')).find(element => element.getClientRects().length > 0) ?? null
}
