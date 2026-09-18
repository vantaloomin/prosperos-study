import { useEffect, useRef, useState } from 'react'
import { SourceMemoryCoverage } from '../workflow/SourceMemoryCoverage'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import { CharacterDialogue, ActorInputs, type DialogueSetup } from './CharacterDialogue'
import { actorInputs } from './characterDialogueRequest'
import type { ModelProfile } from '../models/types'
import type { SceneKey, SceneRun, StagePreview } from './types'

export function StageRequest({ run, step, profiles, onStarted, targets = {} }: { run: SceneRun; step: SceneKey; profiles: ModelProfile[]; onStarted: (id: string) => void; targets?: { review_job_ids?: string[]; item_id?: string } }) {
  const [selected, setSelected] = useState<string[]>([])
  const [preview, setPreview] = useState<{ data: StagePreview; operation: string } | null>(null)
  const action = useAction()
  const [actors, setActors] = usePersistent<DialogueSetup>('roleplay:scene-actors:' + run.id + ':' + run.state.selections['scene-draft'], { enabled: false, actors: [] })
  const changeActors = (value: DialogueSetup) => { setActors(value); setPreview(null) }
  const toggle = (id: string) => { setSelected(selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id]); setPreview(null) }
  const body = { expected_revision: run.revision, key: step, profile_ids: selected, ...targets, ...(step === 'scene-dialogue' && actors.enabled ? { dialogue_actors: actorInputs(actors) } : {}) }
  const prepare = () => action.run(async () => { setPreview({ data: await api<StagePreview>(`/scenes/${run.id}/preview`, body), operation: operationId() }) })
  const start = () => action.run(async () => {
    if (!preview) return
    const result = await api<{ job_ids: string[] }>(`/scenes/${run.id}/stages`, { ...body, preview_hash: preview.data.preview_hash, operation_id: preview.operation })
    onStarted(result.job_ids[0])
    setPreview(null)
  })
  return <section className="scene-request form-stack"><details className="scene-profiles"><summary>{selected.length ? `${selected.length} comparison profiles` : 'Use assigned model · change or compare'}</summary><p className="subtle">Leave empty to inherit this step’s saved model. Select up to four profiles for a deliberate comparison with identical source material.</p>{profiles.map((profile) => <label className="check-row" key={profile.profile_id}><input type="checkbox" checked={selected.includes(profile.profile_id)} disabled={!selected.includes(profile.profile_id) && selected.length >= 4} onChange={() => toggle(profile.profile_id)} />{profile.display_name ?? profile.name}</label>)}</details>
    {step === 'scene-dialogue' && <CharacterDialogue run={run} value={actors} onChange={changeActors} />}
    <ErrorNotice message={action.error} /><button className="button" aria-disabled={action.busy} onClick={prepare}>Preview stage requests</button>
    {preview && <RequestEstimate data={preview.data} busy={action.busy} onStart={start} />}
  </section>
}

function RequestEstimate({ data, busy, onStart }: { data: StagePreview; busy: boolean; onStart: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus(); heading.current?.scrollIntoView({ block: 'nearest' }) }, [])
  return <section className="review-estimate form-stack"><h4 ref={heading} tabIndex={-1}>{data.request_count} planned {data.request_count === 1 ? 'request' : 'requests'}</h4><p className="subtle">Previewing has made no model calls. Input sizes are estimates; provider billing may differ.</p>{data.jobs.map((job, index) => <div key={index} className="review-estimate-row"><strong>{job.name} · {job.profile_name}</strong><span>{job.model} · prompt v{job.prompt_version}</span><StageSources job={job} /></div>)}<button className="button primary" aria-disabled={busy} onClick={onStart}>Generate {data.jobs.length === 1 ? 'proposal' : `${data.jobs.length} proposals`}</button></section>
}


function StageSources({ job }: { job: StagePreview['jobs'][number] }) {
  if (job.dialogue_actors?.length) return <><small>{job.dialogue_actors.length} character calls · ~{job.estimated_input_tokens.toLocaleString()} total input tokens</small><ActorInputs actors={job.dialogue_actors} /></>
  return <><small>~{job.estimated_input_tokens.toLocaleString()} input tokens · {job.source_count} sources</small><SourceMemoryCoverage memory={job.source_memory} /></>
}
