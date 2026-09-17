import { useState } from 'react'
import type { ModelProfile } from '../models/types'
import { SceneProposal } from './SceneWorkspace'
import { StageRequest } from './StageRequest'
import type { SceneJob, SceneKey, SceneRun } from './types'

const disabledStage = (run: SceneRun, step: SceneKey) => run.snapshot.disabled_steps?.includes(step)

const requestsAllowed = (run: SceneRun, ready: boolean) => ready && !run.stale && !run.state.accepted

export function RevisionJobs({ run, step, profiles, targets, ready = true }: { run: SceneRun; step: SceneKey; profiles: ModelProfile[]; targets: { review_job_ids?: string[]; item_id?: string }; ready?: boolean }) {
  const [selected, setSelected] = useState('')
  const jobs = run.jobs.filter((job) => job.step === step && (job.snapshot.item_id ?? '') === (targets.item_id ?? ''))
  const chosen = targets.item_id ? run.state.verifications[targets.item_id] : run.state.selections[step]
  const job = selectedJob(jobs, selected, chosen)
  if (disabledStage(run, step)) return <p className="subtle">This agent was disabled for this scene. You can review and accept the selected prose yourself.</p>
  return <div className="form-stack">
    {!!jobs.length && <label className="field"><span>Saved {step === 'scene-triage' ? 'triage proposals' : 'stage results'}</span><select value={job?.id ?? ''} onChange={(event) => setSelected(event.target.value)}>{jobs.map((item, index) => <option key={item.id} value={item.id}>{index + 1} · {item.snapshot.profile.name} · {item.status}{chosen === item.id ? ' · chosen' : ''}{!item.current_inputs ? ' · earlier inputs' : ''}</option>)}</select></label>}
    {job && <SceneProposal key={job.id} run={run} job={job} onChosen={() => setSelected(job.id)} />}
    {requestsAllowed(run, ready) && <StageRequest key={`${run.revision}:${JSON.stringify(targets)}`} run={run} step={step} profiles={profiles} targets={targets} onStarted={setSelected} />}
  </div>
}

function selectedJob(jobs: SceneJob[], selected: string, chosen?: string) {
  return jobs.find((item) => item.id === selected) ?? jobs.find((item) => item.id === chosen) ?? jobs.at(-1)
}
