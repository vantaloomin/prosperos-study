import { lazy, Suspense, useState, useEffect, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { GitCompareArrows, Sparkles, History, X } from 'lucide-react'
import { readyProfiles } from '../models/profileReadiness'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch } from '../../types'
import type { ModelProfile, ProfileList } from '../models/types'
import { WritingContext } from './writingActions'
import type { MessageReceipt } from './continuation'
import type { Generation, GenerationSummary } from './types'
import { useWritingRequest, type WritingSelection } from './useWritingRequest'
import { InlineGeneration } from './InlineGeneration'
import { DraftActivity } from './DraftActivity'
const GenerationReview = lazy(() => import('./GenerationReview').then((module) => ({ default: module.GenerationReview })))
import { usePreparedBeat } from '../mechanics/usePreparedBeat'
import { defaultAssessmentChoice } from './assessmentTypes'
import type { AssessmentChoice, WritingResult } from './assessmentTypes'
import { AssessmentOptionsDialog } from './AssessmentOptionsDialog'
import { AssessmentHistory } from './AssessmentHistory'
import { ContextPreviewButton } from './ContextPreviewButton'
import { SummaryLauncher } from '../storyMemory/SummaryLauncher'
import { useReviewedContext } from './useReviewedContext'
const KnowledgeChoice = lazy(() => import('./KnowledgeChoice').then(module => ({ default: module.KnowledgeChoice })))
import { characterRequest } from './knowledgeRequest'
const AssessmentPanel = lazy(() => import('./AssessmentPanel'))
const ComparisonSetup = lazy(() => import('./ComparisonSetup'))

interface Props { branch: Branch; onBranch: (id: string) => void; open: boolean; onClose: () => void; onOpen: () => void; children: ReactNode }

export function GenerationControls({ branch, onBranch, open, onClose, onOpen, children }: Props) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const history = useQuery({ queryKey: ['generations', branch.id], queryFn: () => api<GenerationSummary[]>(`/branches/${branch.id}/generations`), refetchInterval: query => hasActiveDrafts(query.state.data) ? 1500 : 10000 })
  const [override, setOverride] = useState('')
  const [knowledge, setKnowledge] = useState('')
  const [selection, setSelection] = usePersistent<WritingSelection | null>(`roleplay:writing-selection:${branch.id}`, null, true)
  const [dismissed, setDismissed] = usePersistent<string[]>(`roleplay:dismissed-drafts:${branch.id}`, [], true)
  useRecoverSelection(history.data, selection, dismissed, setSelection)
  const [comparing, setComparing] = useState(false)
  const [runId, setRunId] = useState('')
  const [assessment, setAssessment] = useState({ id: '', follow: false })
  const [assessmentOptions, setAssessmentOptions] = useState(false)
  const [assessmentChoice, setAssessmentChoice] = useState<AssessmentChoice>(defaultAssessmentChoice)
  const receive = (result: WritingResult) => { setComparing(false); setSelection(selectResult(result, branch.head_id)) }
  const openWriter = (id: string) => { setAssessment({ id: '', follow: false }); setSelection({ id, kind: 'generation', anchor: selectionAnchor(selection) }) }
  useFollowAssessment(selection, openWriter)
  const dismiss = () => { if (selection) setDismissed([...dismissed, selection.id]); setSelection(null) }
  const { prepared, usePrepared, setSkippedBeat } = usePreparedBeat(branch)
  const action = useWritingRequest(branch, setSelection)
  const changeKnowledge = (subject: string) => { setKnowledge(subject); action.clearError() }
  const availableProfiles = profiles.data?.profiles ?? []
  const contextRequest = characterRequest(writerRequest(branch, override, usePrepared, assessmentChoice), knowledge)
  const preview = useReviewedContext(branch.id, contextRequest)
  const generate = () => action.generate({ ...contextRequest, ...preview.input })
  const onSubmitted = (receipt: MessageReceipt) => action.onSubmitted({ receipt, profile: override, usePrepared, choice: assessmentChoice, knowledge })
  const busy = requestBusy(action, history.data, selection)
  const surface = <DraftPresentation selection={selection} onBranch={onBranch} onDismiss={dismiss} onCurrentSettings={onOpen} onWriter={openWriter} />
  const recovery = <><RequestRecovery action={action} onSettings={onOpen} /><SelectionActivity selection={selection} onDraft={setRunId} onAssessment={id => setAssessment({ id, follow: true })} /></>
  return <WritingContext.Provider value={{ onSubmitted, busy, error: action.error, canGenerate: !!availableProfiles.length, surface, anchor: selectionAnchor(selection), recovery }}>{children}{open && <aside className="context-dock writing-dock" aria-label="Writing tools"><header><h2>Writing tools</h2><button className="icon-button" aria-label="Close writing tools" onClick={onClose}><X size={18} /></button></header><div className="dock-content generation-controls"><div className="writer-toolbar"><WriterChoice profiles={availableProfiles} value={override} onChange={setOverride} />
    <button className="text-button" onClick={() => setComparing(true)} disabled={availableProfiles.length < 2}><GitCompareArrows size={15} />Compare</button>
    <ContinueButton busy={busy} available={availableProfiles.length} assessments={assessmentChoice.assessment_profile_ids.length} onClick={generate} />
  </div><div hidden={Boolean(knowledge)}><PreparedChoice prepared={prepared} selected={usePrepared} onSkip={setSkippedBeat} /></div><ErrorNotice message={action.error || profiles.error?.message} />
    <Suspense fallback={<p role="status">Opening knowledge views...</p>}><KnowledgeChoice branchId={branch.id} value={knowledge} onChange={changeKnowledge} /></Suspense>
    <ContextPreviewButton key={branch.id} branchId={branch.id} request={contextRequest} onReviewed={preview.onReviewed} />{preview.notice}
    <div hidden={Boolean(knowledge)}><AssessmentLinks branch={branch} choice={assessmentChoice} onOptions={() => setAssessmentOptions(true)} onSaved={(id) => setAssessment({ id, follow: false })} /></div>
    <SummaryLauncher branch={branch} />
    <DraftHistory history={history.data ?? []} onSelect={setRunId} />
    <AssessmentHistory branchId={branch.id} onSelect={(id) => setAssessment({ id, follow: false })} />
    </div></aside>}
    {comparing && <Suspense fallback={<p role="status">Opening comparison...</p>}><ComparisonSetup branch={branch} profiles={availableProfiles} knowledge={knowledge} usePrepared={usePrepared} onClose={() => setComparing(false)} assessmentChoice={assessmentChoice} onCreated={receive} /></Suspense>}
    <AssessmentOptionsDialog open={assessmentOptions} profiles={availableProfiles} value={assessmentChoice} onChange={setAssessmentChoice} onClose={() => setAssessmentOptions(false)} />
    {assessment.id && <Suspense fallback={<p role="status">Opening assessment...</p>}><AssessmentPanel id={assessment.id} followWriter={assessment.follow} onClose={() => setAssessment({ id: '', follow: false })} onWriter={openWriter} /></Suspense>}
    {runId && <Suspense fallback={<p role="status">Opening drafts…</p>}><GenerationReview id={runId} onClose={() => setRunId('')} onBranch={onBranch} /></Suspense>}
  </WritingContext.Provider>
}

function RequestRecovery({ action, onSettings }: { action: ReturnType<typeof useWritingRequest>; onSettings: () => void }) {
  const { pending, busy, error, retry, clearRejected } = action
  if (!pending && !error) return null
  return <div className="request-recovery"><p role="status">{busy ? 'Preparing the writing request…' : 'The writing request needs attention. Saved story text is kept.'}</p><ErrorNotice message={error} />{pending && !busy && <button className="button" onClick={retry}>Retry continuation</button>}{pending?.rejected && <button className="text-button" onClick={() => { clearRejected(); onSettings() }}>Review current settings and start a new request</button>}</div>
}

function selectResult(result: WritingResult, anchor: string | null): WritingSelection {
  return result.assessment_id ? { id: result.assessment_id, kind: 'assessment', anchor } : { id: result.id!, kind: 'generation', anchor }
}

function selectionAnchor(selection: WritingSelection | null) { return selection?.anchor ?? null }

function hasActiveDrafts(history: GenerationSummary[] | undefined) {
  return history?.some(run => run.statuses.some(status => ['queued', 'running'].includes(status))) ?? false
}

function requestBusy(action: ReturnType<typeof useWritingRequest>, history: GenerationSummary[] | undefined, selection: WritingSelection | null) {
  return action.busy || !!action.pending || hasActiveDrafts(history) || selection?.kind === 'assessment'
}

function SelectionActivity({ selection, onDraft, onAssessment }: { selection: WritingSelection | null; onDraft: (id: string) => void; onAssessment: (id: string) => void }) {
  if (!selection) return null
  if (selection.kind === 'generation') return <DraftActivity id={selection.id} onOpen={() => onDraft(selection.id)} />
  return <AssessmentActivity id={selection.id} onOpen={() => onAssessment(selection.id)} />
}

interface AssessmentStatus { generation_id: string | null; stale: boolean; stopped: number; error: string; jobs: { status: string }[] }
function AssessmentActivity({ id, onOpen }: { id: string; onOpen: () => void }) {
  const query = useQuery({ queryKey: ['assessment', id], queryFn: () => api<AssessmentStatus>(`/assessments/${id}`), refetchInterval: 1500 })
  const label = query.error ? 'Connection to the app lost; assessment status is unknown.' : assessmentLabel(query.data)
  return <div className="draft-activity"><span role="status">{label}</span><button className="text-button" onClick={onOpen}>Open assessment status & controls</button></div>
}
function assessmentLabel(run?: AssessmentStatus) {
  if (!run) return 'Opening saved assessment…'
  if (run.generation_id) return 'Opening the writing request…'
  if (run.stale) return 'The story changed. Review the saved assessment.'
  if (run.stopped) return 'Assessment stopped. Your story is unchanged.'
  if (run.error || run.jobs.some(job => ['error', 'interrupted', 'cancelled'].includes(job.status))) return 'Assessment needs attention. Open its status to recover.'
  if (run.jobs.some(job => ['queued', 'running'].includes(job.status))) return 'Checking the scene before writing…'
  return 'Assessment ready. Review the next step.'
}

function useFollowAssessment(selection: WritingSelection | null, onWriter: (id: string) => void) {
  const id = selection?.kind === 'assessment' ? selection.id : ''
  const query = useQuery({ queryKey: ['assessment', id], queryFn: () => api<{ generation_id: string | null }>(`/assessments/${id}`), enabled: !!id, refetchInterval: id ? 1500 : false })
  useEffect(() => { if (id && query.data?.generation_id) onWriter(query.data.generation_id) }, [id, query.data, onWriter])
}

function DraftPresentation({ selection, onBranch, onDismiss, onCurrentSettings, onWriter }: { selection: WritingSelection | null; onBranch: (id: string) => void; onDismiss: () => void; onCurrentSettings: () => void; onWriter: (id: string) => void }) {
  if (!selection) return null
  return <Suspense fallback={<p role="status">Opening saved work…</p>}>{selection.kind === 'generation'
    ? <InlineGeneration key={selection.id} id={selection.id} onBranch={onBranch} onDismiss={onDismiss} onCurrentSettings={onCurrentSettings} />
    : <AssessmentPanel key={selection.id} id={selection.id} inline followWriter onClose={onDismiss} onWriter={onWriter} />}</Suspense>
}

function useRecoverSelection(history: GenerationSummary[] | undefined, selected: WritingSelection | null, dismissed: string[], onSelect: (value: WritingSelection) => void) {
  const cache = useQueryClient()
  useEffect(() => {
    if (selected) return
    const run = history?.find(item => item.statuses.some(status => ['queued', 'running'].includes(status))) ?? history?.[0]
    if (!run || !run.unaccepted || dismissed.includes(run.id)) return
    let current = true
    void cache.fetchQuery({ queryKey: ['generation', run.id], queryFn: () => api<Generation>(`/generations/${run.id}`) }).then(value => {
      const origin = value.snapshot as Generation['snapshot'] & { branch: { head_id: string | null } }
      if (current) onSelect({ id: run.id, kind: 'generation', anchor: origin.branch.head_id })
    }).catch(() => { /* History remains available; retry on the next successful history poll. */ })
    return () => { current = false }
  }, [history, selected, dismissed, onSelect, cache])
}

function writerRequest(branch: Branch, selected: string, usePrepared: boolean, choice: AssessmentChoice) {
  return { expected_revision: branch.revision, profile_ids: selected ? [selected] : [], use_prepared_beat: usePrepared, ...choice }
}

function WriterChoice({ profiles, value, onChange }: { profiles: ModelProfile[]; value: string; onChange: (id: string) => void }) {
  if (!profiles.length) return <span className="subtle">Add a model in Settings to generate.</span>
  return <select aria-label="Writer for this request" value={value} onChange={(e) => onChange(e.target.value)}><option value="">Primary Writer / step default</option>{profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)}</select>
}

function DraftHistory({ history, onSelect }: { history: GenerationSummary[]; onSelect: (id: string) => void }) {
  if (!history.length) return null
  return <details className="draft-history"><summary><History size={13} />Saved drafts ({history.length})</summary><div>{history.map((run, index) => <button className="text-button" key={run.id} onClick={() => onSelect(run.id)}>Draft {history.length - index} · {new Date(run.created_at).toLocaleString()}</button>)}</div></details>
}


function PreparedChoice({ prepared, selected, onSkip }: { prepared: Branch['mechanics']['pending']; selected: boolean; onSkip: (id: string) => void }) {
  if (!prepared) return null
  return <label className="prepared-choice check-row"><input type="checkbox" checked={selected} disabled={prepared.stale} onChange={(e) => onSkip(e.target.checked ? '' : prepared.id)} /><span>{prepared.stale ? 'Prepared beat is outdated; writing without it.' : `Use prepared beat: ${prepared.label}`}</span></label>
}

function AssessmentLinks({ branch, choice, onOptions, onSaved }: { branch: Branch; choice: AssessmentChoice; onOptions: () => void; onSaved: (id: string) => void }) {
  return <>{branch.mechanics.automatic_assessment && <div className="prepared-choice assessment-controls"><button className="text-button" onClick={onOptions}>Beat assessment options</button><span className="subtle">{choice.assess_beat ? `Beat checks before writing: up to ${Math.max(1, choice.assessment_profile_ids.length)}.` : 'Skipping assessment for this request.'}</span></div>}
    {branch.mechanics.assessment && <button className="text-button" onClick={() => onSaved(branch.mechanics.assessment!.id)}>Open saved beat assessment</button>}</>
}

function ContinueButton({ busy, available, assessments, onClick }: { busy: boolean; available: number; assessments: number; onClick: () => Promise<void> }) {
  return <button className="button quiet" disabled={busy || !available || assessments > 4} aria-busy={busy} onClick={() => void onClick()}><Sparkles size={15} />Continue story</button>
}
