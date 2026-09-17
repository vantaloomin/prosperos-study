import { lazy, Suspense, useRef, useState, useEffect, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { GitCompareArrows, Sparkles, History, X } from 'lucide-react'
import { readyProfiles } from '../models/profileReadiness'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import type { ModelProfile, ProfileList } from '../models/types'
import { WritingContext } from './writingActions'
import { continuationRequest, type MessageReceipt } from './continuation'
import type { GenerationSummary } from './types'
const GenerationReview = lazy(() => import('./GenerationReview').then((module) => ({ default: module.GenerationReview })))
import { usePreparedBeat } from '../mechanics/usePreparedBeat'
import { defaultAssessmentChoice } from './assessmentTypes'
import type { AssessmentChoice, WritingResult } from './assessmentTypes'
import { AssessmentOptionsDialog } from './AssessmentOptionsDialog'
import { AssessmentHistory } from './AssessmentHistory'
import { ContextPreviewButton } from './ContextPreviewButton'
const AssessmentPanel = lazy(() => import('./AssessmentPanel'))
const ComparisonSetup = lazy(() => import('./ComparisonSetup'))

interface Props { branch: Branch; onBranch: (id: string) => void; open: boolean; onClose: () => void; children: ReactNode }

export function GenerationControls({ branch, onBranch, open, onClose, children }: Props) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const history = useQuery({ queryKey: ['generations', branch.id], queryFn: () => api<GenerationSummary[]>(`/branches/${branch.id}/generations`) })
  const [override, setOverride] = useState('')
  const current = useRef(true)
  useEffect(() => { current.current = true; return () => { current.current = false } }, [])
  const [comparing, setComparing] = useState(false)
  const [runId, setRunId] = useState('')
  const [assessment, setAssessment] = useState({ id: '', follow: false })
  const [assessmentOptions, setAssessmentOptions] = useState(false)
  const [assessmentChoice, setAssessmentChoice] = useState<AssessmentChoice>(defaultAssessmentChoice)
  const receive = (result: WritingResult) => { if (result.assessment_id) setAssessment({ id: result.assessment_id, follow: true }); else setRunId(result.id!) }
  const openWriter = (id: string) => { setAssessment({ id: '', follow: false }); setRunId(id) }
  const { prepared, usePrepared, setSkippedBeat } = usePreparedBeat(branch)
  const action = useAction()
  const availableProfiles = profiles.data?.profiles ?? []
  const contextRequest = writerRequest(branch, override, usePrepared, assessmentChoice)
  const generate = () => action.run(async () => {
    const result = await api<WritingResult>(`/branches/${branch.id}/generations`, { operation_id: operationId(), ...contextRequest })
    receive(result)
  })
  const onSubmitted = (receipt: MessageReceipt) => action.run(async () => {
    const next = await api<Branch>(`/branches/${receipt.branch_id}`)
    if (!current.current) return
    const request = continuationRequest(next, receipt, override, usePrepared, assessmentChoice)
    const result = await api<WritingResult>(`/branches/${receipt.branch_id}/generations`, request)
    if (current.current) receive(result)
  })
  return <WritingContext.Provider value={{ onSubmitted, busy: action.busy, error: action.error, canGenerate: !!availableProfiles.length }}>{children}{open && <aside className="context-dock writing-dock" aria-label="Writing tools"><header><h2>Writing tools</h2><button className="icon-button" aria-label="Close writing tools" onClick={onClose}><X size={18} /></button></header><div className="dock-content generation-controls"><div className="writer-toolbar"><WriterChoice profiles={availableProfiles} value={override} onChange={setOverride} />
    <button className="text-button" onClick={() => setComparing(true)} disabled={availableProfiles.length < 2}><GitCompareArrows size={15} />Compare</button>
    <ContinueButton busy={action.busy} available={availableProfiles.length} assessments={assessmentChoice.assessment_profile_ids.length} onClick={generate} />
  </div><PreparedChoice prepared={prepared} selected={usePrepared} onSkip={setSkippedBeat} /><ErrorNotice message={action.error || profiles.error?.message} />
    <ContextPreviewButton key={branch.id} branchId={branch.id} request={contextRequest} />
    <AssessmentLinks branch={branch} choice={assessmentChoice} onOptions={() => setAssessmentOptions(true)} onSaved={(id) => setAssessment({ id, follow: false })} />
    <DraftHistory history={history.data ?? []} onSelect={setRunId} />
    <AssessmentHistory branchId={branch.id} onSelect={(id) => setAssessment({ id, follow: false })} />
    </div></aside>}
    {comparing && <Suspense fallback={<p role="status">Opening comparison...</p>}><ComparisonSetup branch={branch} profiles={availableProfiles} usePrepared={usePrepared} onClose={() => setComparing(false)} assessmentChoice={assessmentChoice} onCreated={receive} /></Suspense>}
    <AssessmentOptionsDialog open={assessmentOptions} profiles={availableProfiles} value={assessmentChoice} onChange={setAssessmentChoice} onClose={() => setAssessmentOptions(false)} />
    {assessment.id && <Suspense fallback={<p role="status">Opening assessment...</p>}><AssessmentPanel id={assessment.id} followWriter={assessment.follow} onClose={() => setAssessment({ id: '', follow: false })} onWriter={openWriter} /></Suspense>}
    {runId && <Suspense fallback={<p role="status">Opening drafts…</p>}><GenerationReview id={runId} onClose={() => setRunId('')} onBranch={onBranch} /></Suspense>}
  </WritingContext.Provider>
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
