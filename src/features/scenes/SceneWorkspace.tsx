import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import type { ModelProfile } from '../models/types'
import type { Routing } from '../workflow/types'
import { BeatEditor } from './BeatEditor'
import { SceneChance } from './SceneChance'
import { BeatView, SceneArtifact } from './SceneArtifacts'
import { SelectedDraft } from './DraftArtifacts'
import { SceneReviews } from './SceneReviews'
import { RevisionWorkspace } from './RevisionWorkspace'
import { PatchWorkspace } from './PatchWorkspace'
import { ContinuityWorkspace } from './ContinuityWorkspace'
import { ManualSceneAcceptance } from './ManualSceneAcceptance'
import { StageRequest } from './StageRequest'
import { enabledSceneSteps, planningStep, sceneSteps, sceneWorking, type SceneJob, type SceneKey, type SceneRun } from './types'
import { useScene } from './useScene'
import { useSceneFocus } from './useSceneFocus'

type WorkspaceProps = { profiles: ModelProfile[]; branch: Branch; routing: Routing; onBranch: (id: string) => void }

export function SceneWorkspace({ id, ...props }: WorkspaceProps & { id: string }) {
  const query = useScene(id)
  if (query.isPending) return <Loading label="Opening the scene plan…" />
  return <><ErrorNotice message={query.error?.message} />{query.data && <SceneRunView run={query.data} {...props} />}</>
}

const failedPatchWriter = (run: SceneRun, key: SceneKey) => ['scene-patch', 'scene-dialogue-patch'].includes(key) && !!run.patch?.check && !run.patch.checked
const stepLocked = (run: SceneRun, key: SceneKey) => !!run.state.accepted || run.stale || (planningStep(key) && !!run.state.gate_a) || failedPatchWriter(run, key)
const defaultStage = (run: SceneRun): SceneKey | '' => run.next_step || enabledSceneSteps(run).at(-1)?.key || ''

function SceneRunView({ run, profiles, branch, routing, onBranch }: WorkspaceProps & { run: SceneRun }) {
  const [stage, setStage] = useState<SceneKey | ''>('')
  const [editing, setEditing] = useState(false)
  const step = stage || defaultStage(run)
  const steps = enabledSceneSteps(run)
  return <section className="scene-workspace form-stack"><header><h3>{run.title}</h3><p className="subtle">Started on {run.snapshot.branch.name} · Story revision {run.snapshot.branch.revision}</p><p className="scene-direction">{run.snapshot.direction}</p></header>
    <SceneNotices run={run} />
    <SceneChance run={run} />
    <WorkflowSwitchNotice run={run} />
    <div className="scene-stage-nav" style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }} aria-label="Scene stages">{steps.map((item, index) => <button key={item.key} aria-pressed={step === item.key} onClick={() => setStage(item.key)}><small>{index + 1} · {run.state.selections[item.key] ? 'Chosen' : 'To do'}</small><strong>{item.name}</strong></button>)}</div>
    {step && <SceneStage key={step} step={step} run={run} profiles={profiles} onChosen={() => setStage('')} onEdit={() => setEditing(true)} />}
    {!run.state.gate_a && !run.next_step && <PlanApproval run={run} />}
    {run.draft && <SelectedDraft run={run} onRedraft={() => setStage('scene-draft')} />}
    <SceneReviewWork run={run} profiles={profiles} branch={branch} routing={routing} />
    <PatchWorkspace run={run} profiles={profiles} />
    <ContinuityWorkspace run={run} profiles={profiles} onBranch={onBranch} />
    <ManualSceneAcceptance run={run} onBranch={onBranch} />
    <details className="input-inspector"><summary>Director decisions & preserved edits</summary>{run.decisions.map((decision) => <div key={decision.id}><h4>{decision.revision} · {decision.kind} · {new Date(decision.created_at).toLocaleString()}</h4><pre>{JSON.stringify(decision.payload, null, 2)}</pre></div>)}</details>
    {editing && run.plan && <BeatEditor run={run} plan={run.plan} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); setStage('scene-brief') }} />}
  </section>
}

function SceneNotices({ run }: { run: SceneRun }) {
  if (run.state.accepted) return null
  return <>{run.stale && <p role="status" className="scene-notice">The Story has changed since this plan began. Its proposals are preserved. A checked scene with a selected continuity proposal may be accepted on a new branch; other work needs a new plan.</p>}{run.state.gate_a && <ApprovedNotice run={run} />}</>
}

function SceneReviewWork({ run, profiles, branch, routing }: Omit<WorkspaceProps, 'onBranch'> & { run: SceneRun }) {
  if (!run.state.gate_a || run.state.accepted) return null
  return <><SceneReviews run={run} profiles={profiles} branch={branch} routing={routing} /><RevisionWorkspace run={run} profiles={profiles} routing={routing} /></>
}

function ApprovedNotice({ run }: { run: SceneRun }) {
  const panel = useSceneFocus('approved')
  return <section ref={panel} tabIndex={-1} role="status" className="scene-notice">Plan approved · {new Date(run.state.gate_a!.approved_at).toLocaleString()}. Drafting is available. Story text and canon stay unchanged.{run.state.gate_a!.note && <p>{run.state.gate_a!.note}</p>}</section>
}

function SceneStage({ step, run, profiles, onChosen, onEdit }: { step: SceneKey; run: SceneRun; profiles: ModelProfile[]; onChosen: () => void; onEdit: () => void }) {
  const [selected, setSelected] = useState('')
  const jobs = run.jobs.filter((job) => job.step === step)
  const job = currentJob(jobs, selected, run.state.selections[step])
  const ready = stageReady(run, step)
  const locked = stepLocked(run, step)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus({ preventScroll: true }); heading.current?.scrollIntoView({ block: 'nearest' }) }, [])
  return <div className="form-stack"><h4 ref={heading} tabIndex={-1}>{sceneSteps.find((item) => item.key === step)?.name}</h4>
    {!ready && <p className="subtle">{!planningStep(step) && !run.state.gate_a ? 'Approve the beat plan and continuity brief before drafting.' : 'Choose the preceding stage’s result before preparing this step.'}</p>}
    <JobSelect jobs={jobs} job={job} chosen={run.state.selections[step]} onSelect={setSelected} />
    {job && <SceneProposal key={job.id} run={run} job={job} onChosen={onChosen} />}
    {step === 'scene-beats' && run.plan && <EditedPlan run={run} locked={locked} onEdit={onEdit} />}
    {ready && !locked && <StageRequest key={`${step}:${run.revision}`} run={run} step={step} profiles={profiles} onStarted={setSelected} />}
  </div>
}

function currentJob(jobs: SceneJob[], selected: string, chosen?: string) {
  return jobs.find((item) => item.id === selected) ?? jobs.find((item) => item.id === chosen) ?? jobs.at(-1)
}

function stageReady(run: SceneRun, step: SceneKey) {
  const steps = enabledSceneSteps(run)
  const position = steps.findIndex((item) => item.key === step)
  return (planningStep(step) || !!run.state.gate_a) && steps.slice(0, position).every((item) => !!run.state.selections[item.key])
}

function JobSelect({ jobs, job, chosen, onSelect }: { jobs: SceneJob[]; job?: SceneJob; chosen?: string; onSelect: (value: string) => void }) {
  if (!jobs.length) return null
  return <label className="field"><span>Saved proposals for this stage</span><select value={job?.id ?? ''} onChange={(event) => onSelect(event.target.value)}>{jobs.map((item, index) => <option key={item.id} value={item.id}>{index + 1} · {item.snapshot.profile.name} · {item.status}{chosen === item.id ? ' · chosen' : ''}{!item.current_inputs ? ' · earlier plan' : ''}</option>)}</select></label>
}

function EditedPlan({ run, locked, onEdit }: { run: SceneRun; locked: boolean; onEdit: () => void }) {
  return <section className="scene-edited form-stack">{run.state.beat_edit && <><h4>Your edited beat plan</h4><BeatView plan={run.state.beat_edit} /></>}{!locked && <button className="button" onClick={onEdit}>Edit selected beat plan</button>}</section>
}

export function SceneProposal({ job, run, onChosen }: { job: SceneJob; run: SceneRun; onChosen: () => void }) {
  const action = useAction()
  const panel = useSceneFocus(`${job.id}:${job.status}:${action.busy}`)
  const locked = action.busy || stepLocked(run, job.step) || !job.current_inputs
  const chosen = proposalChosen(run, job)
  const choose = (option?: string) => action.run(async () => {
    if (locked || chosen) return
    await api(`/scenes/${run.id}/choose`, { operation_id: operationId(), expected_revision: run.revision, job_id: job.id, option_id: option ?? null })
    onChosen()
  })
  const control = (kind: string) => action.run(async () => { await api(`/scene-jobs/${job.id}/${kind}`, {}) })
  return <section ref={panel} tabIndex={-1} aria-label={`Proposal from ${job.snapshot.profile.name}`} className="scene-proposal form-stack"><div className="candidate-meta"><span>{job.snapshot.profile.config.model} · prompt v{job.snapshot.prompt.number}</span><span role="status">{job.status} · attempt {job.attempt}</span></div><ErrorNotice message={action.error || job.error} />
    {!job.current_inputs && <p className="subtle">This proposal uses earlier choices. It remains available for reference.</p>}
    <SceneArtifact job={job} run={run} disabled={locked} onChoose={choose} />
    {job.result && job.step !== 'scene-options' && <button className="button" aria-disabled={locked || chosen} onClick={() => choose()}>{chosen ? 'Result selected' : 'Use this stage result'}</button>}
    <JobControls job={job} busy={action.busy} onControl={control} />
    <details className="input-inspector"><summary>Reveal exact inputs and raw output (may include private background)</summary><h4>Prompt</h4><pre>{job.snapshot.prompt.template}</pre><h4>Sources and proposed inputs</h4><pre>{JSON.stringify(JSON.parse(job.snapshot.content), null, 2)}</pre><h4>Raw output</h4><pre>{job.output || 'No text returned yet.'}</pre><h4>Reported usage</h4><pre>{JSON.stringify(job.usage, null, 2)}</pre></details><SceneAttempts job={job} />
  </section>
}

function proposalChosen(run: SceneRun, job: SceneJob) {
  return job.step === 'scene-verify' ? run.state.verifications[job.snapshot.item_id ?? ''] === job.id : run.state.selections[job.step] === job.id
}

function JobControls({ job, busy, onControl }: { job: SceneJob; busy: boolean; onControl: (kind: string) => void }) {
  if (sceneWorking(job)) return <><p className="subtle">You can close this view while the specialist works. Its result will remain here.</p><pre className="scene-stream" aria-label="Partial proposal">{job.output || 'Waiting for the first text…'}</pre><button className="button" aria-disabled={busy} onClick={() => onControl('cancel')}>Stop this specialist</button></>
  if (job.status === 'done') return null
  return <button className="button" aria-disabled={busy} onClick={() => onControl('retry')}>Retry original stage inputs</button>
}

function SceneAttempts({ job }: { job: SceneJob }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['scene-attempts', job.id, job.attempt, job.status], queryFn: () => api<{ attempt: number; status: string; output: string; error: string }[]>(`/scene-jobs/${job.id}/attempts`), enabled: open })
  if (job.attempt < 2) return null
  return <details className="input-inspector" onToggle={(event) => setOpen(event.currentTarget.open)}><summary>Preserved attempts</summary><ErrorNotice message={query.error?.message} />{query.data?.map((attempt) => <div key={attempt.attempt}><h4>Attempt {attempt.attempt} · {attempt.status}</h4><p>{attempt.error}</p><pre>{attempt.output || 'No text returned.'}</pre></div>)}</details>
}

function PlanApproval({ run }: { run: SceneRun }) {
  const [note, setNote] = useState('')
  const action = useAction()
  const approve = () => action.run(async () => { await api(`/scenes/${run.id}/approve`, { operation_id: operationId(), expected_revision: run.revision, note }) })
  if (run.state.gate_a) return <p className="scene-direction">{run.state.gate_a.note || 'Approved with no additional note.'}</p>
  return <section className="scene-gate form-stack"><h4>Director approval · Beat plan</h4><p>Review your direction and any selected planning results. Approval makes drafting available without advancing the Story.</p><label className="field"><span>Approval note (optional)</span><textarea rows={2} maxLength={5000} value={note} onChange={(event) => setNote(event.target.value)} /></label><ErrorNotice message={action.error} /><button className="button primary" disabled={action.busy || run.stale} onClick={approve}>Approve this scene plan</button></section>
}

function WorkflowSwitchNotice({ run }: { run: SceneRun }) {
  return <>
    {!!run.snapshot.disabled_steps?.length && <p className="scene-notice">This scene uses the agent switches saved when it began. Disabled checks are skipped, with manual acceptance available after a complete draft. Start a new scene to use changed switches.</p>}
    {run.snapshot.disabled_steps?.includes('scene-draft') && <p className="scene-notice">Scene drafting is disabled. Use the Story composer to write your own prose.</p>}
  </>
}
