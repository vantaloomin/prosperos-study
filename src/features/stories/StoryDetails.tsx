import { lazy, Suspense, useState } from 'react'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { Field, TextField } from '../../components/Fields'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Selection, Story } from '../../types'

const StoryAgents = lazy(() => import('../prompts/AgentTemplates').then(module => ({ default: module.StoryAgents })))

const TranscriptExport = lazy(() => import('../export/TranscriptExport').then((module) => ({ default: module.TranscriptExport })))
const Archives = lazy(() => import('../export/Archives').then((module) => ({ default: module.Archives })))
const StoryPreferences = lazy(() => import('./StoryPreferences').then((module) => ({ default: module.StoryPreferences })))

export function StoryDetails({ story, branchId, onClose, onOpen }: { story: Story; branchId: string; onClose: () => void; onOpen: (selection: Selection) => void }) {
  const [revision] = useState(story.revision)
  const [title, setTitle] = useState(story.title)
  const [premise, setPremise] = useState(story.premise)
  const [archived, setArchived] = useState(story.archived)
  const [settings, setSettings] = useState(story.settings)
  const [preferences, setPreferences] = useState(false)
  const [agents, setAgents] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [archiving, setArchiving] = useState(false)
  const action = useAction()
  const save = () => action.run(async () => {
    await api(`/stories/${story.id}`, { title, premise, archived, settings, expected_revision: revision }, 'PUT')
    onClose()
  })
  const dirty = title !== story.title || premise !== story.premise || archived !== story.archived || JSON.stringify(settings) !== JSON.stringify(story.settings)
  if (agents) return <Modal open wide title="Story agents" description="Choose the writing partners and guidance for this Story." onClose={onClose}><div className="dialog-body"><Suspense fallback={<Loading />}><StoryAgents storyId={story.id} /></Suspense></div></Modal>
  return <><Modal open onClose={onClose} title="Story setup" description="A title, a direction, and room to grow."><div className="dialog-body form-stack"><Field label="Title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} /><TextField label="Story brief" rows={8} value={premise} onChange={(e) => setPremise(e.target.value)} hint="Premise, tone, and standing guidance for this story. Author’s notes belong to a path; Scene goal directs one planned scene. Changes affect future writing." /><details className="advanced-settings" onToggle={(event) => setPreferences(event.currentTarget.open)}><summary>Writing preferences</summary>{preferences && <Suspense fallback={<Loading label="Opening preferences…" />}><StoryPreferences value={settings} onChange={setSettings} /></Suspense>}</details><label className="check-row"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />Archive this story</label><button className="button" disabled={dirty} onClick={() => setAgents(true)}>Agents</button>{dirty && <p className="subtle">Save Story setup before changing agents.</p>}<button className="button" onClick={() => setExporting(true)}>Export transcript</button><button className="button" onClick={() => setArchiving(true)}>Private archive & recovery</button><ErrorNotice message={action.error} /></div><footer className="dialog-footer"><span className="subtle">Archived stories can be restored.</span><button className="button primary" disabled={action.busy || !title.trim()} onClick={save}>Save story setup</button></footer></Modal>
    {exporting && <Suspense fallback={<Loading label="Opening export…" />}><TranscriptExport story={story} initialBranchId={branchId} onClose={() => setExporting(false)} /></Suspense>}
    {archiving && <Modal open onClose={() => setArchiving(false)} title="A copy of this world" description="Preserve the saved paths and the details that made them possible." wide><div className="dialog-body"><Suspense fallback={<Loading label="Opening archives…" />}><Archives story={story} selection={{ storyId: story.id, branchId }} onOpen={onOpen} /></Suspense></div></Modal>}
  </>
}
