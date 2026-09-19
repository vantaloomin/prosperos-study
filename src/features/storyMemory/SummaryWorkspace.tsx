import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch, StorySummary } from '../../types'
import { SummarySetup } from './SummarySetup'
import { SummaryResults } from './SummaryResults'
import { MaintenancePanel } from './MaintenancePanel'
import { BackfillSetup } from './BackfillSetup'
import { MaintenanceBatch } from './MaintenanceBatch'
import { AuthorControls } from './AuthorControls'
import { SceneRehearsal } from './SceneRehearsal'
import { RelationshipPanel } from './RelationshipPanel'

export default function SummaryWorkspace({ branch, onClose, focusOnClose }: { branch: Branch; onClose: () => void; focusOnClose: () => HTMLElement | null }) {
  const [section, setSection] = useState<'summaries' | 'decisions' | 'rehearsal' | 'relationships'>('summaries')
  const [view, setView] = useState({ kind: 'excerpts', id: '' })
  const review = (id: string) => setView({ kind: 'run', id })
  return <Modal open wide title="Story memory" description="Give earlier passages more ways to be found. Review summaries against their exact sources; the manuscript remains yours." onClose={onClose} focusOnClose={focusOnClose}>
    <div className="dialog-body form-stack"><div className="import-downloads" aria-label="Story memory sections"><button className="button" aria-pressed={section === 'summaries'} onClick={() => setSection('summaries')}>Reviewed summaries</button><button className="button" aria-pressed={section === 'decisions'} onClick={() => setSection('decisions')}>Author decisions</button><button className="button" aria-pressed={section === 'rehearsal'} onClick={() => setSection('rehearsal')}>Scene rehearsal</button><button className="button" aria-pressed={section === 'relationships'} onClick={() => setSection('relationships')}>Relationship links</button></div>
      {section === 'relationships' ? <RelationshipPanel key={branch.id} branch={branch} /> : section === 'decisions' ? <AuthorControls key={branch.id} branch={branch} /> : section === 'rehearsal' ? <SceneRehearsal key={branch.id} branch={branch} onDecisions={() => setSection('decisions')} /> : <><RecallSwitch storyId={branch.story_id} />
      <MaintenancePanel branch={branch} onBackfill={() => setView({ kind: 'backfill', id: '' })} onBatch={id => setView({ kind: 'batch', id })} />
      <MemoryView branch={branch} view={view} onView={setView} />
      <SummaryHistory branchId={branch.id} onOpen={review} /></>}
    </div><footer className="dialog-footer"><button className="button" onClick={onClose}>Back to writing</button></footer>
  </Modal>
}

function RecallSwitch({ storyId }: { storyId: string }) {
  const query = useQuery({ queryKey: ['story', storyId], queryFn: () => api<StorySummary>('/stories/' + storyId) })
  const action = useAction()
  const [pending, setPending] = useState<boolean | null>(null)
  const story = query.data
  const memory = (story?.settings.memory ?? {}) as { mode?: string; summary_recall?: boolean }
  const toggle = async (enabled: boolean) => {
    setPending(enabled)
    await action.run(async () => {
      if (!story) return
      await api('/stories/' + storyId, { expected_revision: story.revision, title: story.title, premise: story.premise,
        archived: story.archived, settings: { ...story.settings, memory: { ...memory, summary_recall: enabled } } }, 'PUT')
    })
    setPending(null)
  }
  return <div className="prepared-card"><label className="check-row"><input type="checkbox" checked={pending ?? memory.summary_recall ?? false} disabled={!story || action.busy || memory.mode !== 'long'} onChange={event => toggle(event.target.checked)} />Use reviewed summaries for story recall</label>
    <p className="subtle">{memory.mode === 'long' ? 'Reviewed summaries help the writer, scene work, permitted reviewers and sidebar find original prose. Allow reviewed summaries in context is a separate Writing preference: it can supply a shorter interpretation with exact grounding quotes when space is tight. Source permissions still apply. Existing scene plans and sidebar questions keep their frozen memory. Recall makes no extra model calls.' : 'Select Long story in Writing preferences to use summary-assisted recall. You can prepare and review summaries here at any time.'}</p>
    <ErrorNotice message={query.error?.message || action.error} />
  </div>
}

function SummaryHistory({ branchId, onOpen }: { branchId: string; onOpen: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(0)
  const query = useQuery({ queryKey: ['summary-history', branchId, page], queryFn: () => api<{ id: string; branch_name: string; created_at: string }[]>('/branches/' + branchId + '/summaries?offset=' + page * 50), enabled: open })
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Saved requests in this Story</summary><div className="form-stack authoring-history"><ErrorNotice message={query.error?.message} />
    <p className="subtle">Requests from other paths are kept for inspection. Saving on this path requires all cited originals to remain in its history.</p>
    {query.data?.map(run => <button className="prompt-row" key={run.id} onClick={() => onOpen(run.id)}>{run.branch_name} · {new Date(run.created_at).toLocaleString()}</button>)}
    <div className="import-downloads"><button className="button" disabled={!page || query.isFetching} onClick={() => setPage(page - 1)}>Newer requests</button><button className="button" disabled={query.data?.length !== 50 || query.isFetching} onClick={() => setPage(page + 1)}>Older requests</button></div>
  </div></details>
}


function MemoryView({ branch, view, onView }: { branch: Branch; view: { kind: string; id: string }; onView: (view: { kind: string; id: string }) => void }) {
  const back = () => onView({ kind: 'excerpts', id: '' })
  const review = (id: string) => onView({ kind: 'run', id })
  if (view.kind === 'run') return <SummaryResults key={view.id} branch={branch} runId={view.id} onNew={back} />
  if (view.kind === 'backfill') return <BackfillSetup branch={branch} onBack={back} onStarted={id => onView({ kind: 'batch', id })} />
  if (view.kind === 'batch') return <MaintenanceBatch key={view.id} id={view.id} onBack={back} onReview={review} />
  return <SummarySetup branch={branch} onStarted={review} />
}
