import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { ModelProfile } from '../models/types'
import { PatchChange } from './PatchArtifacts'
import { patchSteps } from './patchTypes'
import { RevisionJobs } from './RevisionJobs'
import type { SceneKey, SceneRun } from './types'
import { useSceneFocus } from './useSceneFocus'

export function PatchWorkspace({ run, profiles }: { run: SceneRun; profiles: ModelProfile[] }) {
  const focus = useSceneFocus(`patch-round:${run.state.patch_round}`)
  if (!run.patch) return null
  const steps = patchSteps.filter((step) => step.key !== 'scene-dialogue-patch' || run.snapshot.dialogue_split)
  return <section ref={focus} tabIndex={-1} className="scene-revisions form-stack"><h3>Apply the approved changes</h3><p>Each proposal preserves the original draft and links its changes to your approved package. Choose a result at each step.</p>
    {run.patch.no_changes_required ? <p className="scene-notice">This package authorizes no text changes. The original draft is retained without patch requests.</p> : steps.map((step, index) => <PatchStage key={`${step.key}:${run.state.patch_round}`} run={run} profiles={profiles} step={step} index={index} preceding={steps.slice(0, index).map((item) => item.key)} />)}
    <PatchStatus run={run} />
    <details className="input-inspector"><summary>Selected revised draft and change log</summary><p className="subtle">Proposed Story text · {run.patch.complete ? 'all patch writers selected' : 'patching in progress'}</p><pre>{run.patch.text}</pre>{run.patch.changes.map((edit) => <PatchChange key={edit.id} edit={edit} />)}</details>
  </section>
}

function PatchStage({ run, profiles, step, index, preceding }: { run: SceneRun; profiles: ModelProfile[]; step: typeof patchSteps[number]; index: number; preceding: SceneKey[] }) {
  const [open, setOpen] = useState(!run.state.selections[step.key])
  return <details className="input-inspector" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}><summary>{index + 1} · {step.name}{run.state.selections[step.key] ? ' · chosen' : ''}</summary>
    <RevisionJobs run={run} step={step.key} profiles={profiles} targets={{}} ready={patchReady(run, step.key, preceding)} />
  </details>
}

function patchReady(run: SceneRun, step: SceneKey, preceding: SceneKey[]) {
  if (!preceding.every((key) => !!run.state.selections[key])) return false
  if (step === 'scene-patch-check') return !!run.patch?.complete && !run.patch.blocked
  return !run.state.selections['scene-patch-check']
}

function PatchStatus({ run }: { run: SceneRun }) {
  return run.state.accepted ? <p className="subtle">This checked revision is preserved with the accepted scene.</p> : <PendingPatchStatus run={run} />
}

function PendingPatchStatus({ run }: { run: SceneRun }) {
  const action = useAction()
  const patch = run.patch!
  const repair = () => action.run(async () => { await api(`/scenes/${run.id}/repair-patch`, { operation_id: operationId(), expected_revision: run.revision }) })
  if (patch.checked) return <p role="status" className="scene-notice">{patch.no_changes_required ? 'No patch check needed.' : 'Selected changed-passage check passed.'} Review continuity below before accepting this scene.</p>
  if (patch.blocked && patch.complete) return <p role="status">A writer left an item unresolved. Revisit its proposal or the revision package before checking the passages.</p>
  if (!patch.check) return run.state.patch_round ? <p role="status">One correction is available in this round. The previous patch and failed check are included in its inputs.</p> : null
  return <div className="form-stack"><p role="status">The selected check needs correction. {run.state.patch_round ? 'The correction has been used. Revisit triage and the approved package, or redraft with the director.' : 'Request one correction using the same approved package; no model call starts until you preview and generate it.'}</p><ErrorNotice message={action.error} />{!run.state.patch_round && <button className="button" disabled={run.stale || action.busy} onClick={repair}>Prepare one patch correction</button>}</div>
}
import { useState } from 'react'
