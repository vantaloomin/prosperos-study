import { useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import { ModelChoices } from '../authoring/AuthoringModels'
import { readyProfiles } from '../models/profileReadiness'
import type { ProfileList } from '../models/types'
import { BatchLimits } from './MaintenancePanel'
import type { BackfillPreview } from './maintenanceTypes'

export function BackfillSetup({ branch, onStarted, onBack }: { branch: Branch; onStarted: (id: string) => void; onBack: () => void }) {
  const [limits, setLimits] = useState({ batch_size: 4, max_batches: 1 })
  const [compare, setCompare] = useState(false)
  const [profiles, setProfiles] = useState<string[]>([])
  const [prepared, setPrepared] = useState<BackfillPreview | null>(null)
  const action = useAction()
  const models = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  const change = (update: () => void) => { update(); setPrepared(null) }
  const request = { expected_revision: branch.revision, ...limits, profile_ids: profiles }
  const preview = () => action.run(async () => setPrepared(await api<BackfillPreview>('/branches/' + branch.id + '/summary-backfill-preview', request)))
  const start = () => action.run(async () => {
    if (!prepared) return
    const batch = await api<{ id: string }>('/branches/' + branch.id + '/summary-backfill', { ...request, operation_id: operationId(), preview_hash: prepared.preview_hash })
    onStarted(batch.id)
  })
  return <section className="form-stack"><div className="section-heading"><h3 ref={heading} tabIndex={-1}>Prepare earlier passages</h3><button className="text-button" onClick={onBack}>Choose individual excerpts</button></div>
    <p className="subtle">Start with the earliest unrequested accepted excerpts on this path. Every source stays intact; previous requests and author exclusions are preserved. A long chapter can continue across later capped batches.</p>
    <BatchLimits value={limits} onChange={next => change(() => setLimits({ ...limits, ...next }))} />
    {models.data && <ModelChoices profiles={models.data.profiles} selected={profiles} compare={compare} onMode={next => change(() => { setCompare(next); setProfiles([]) })} onChange={next => change(() => setProfiles(next))} />}
    <p>Up to {limits.max_batches * Math.max(1, profiles.length)} model requests. Preview shows the actual count and estimated input before anything is queued.</p>
    <ErrorNotice message={action.error || models.error?.message} />
    <button className="button" disabled={action.busy || invalidModels(models.data, compare, profiles.length)} onClick={preview}>{prepared ? 'Refresh backfill preview' : 'Preview earlier passages'}</button>
    {prepared && <BackfillReview key={prepared.preview_hash} prepared={prepared} busy={action.busy} onStart={start} />}
  </section>
}

function invalidModels(models: ProfileList | undefined, compare: boolean, count: number) {
  return !models?.profiles.length || (compare && (count < 2 || count > 4))
}

function BackfillReview({ prepared, busy, onStart }: { prepared: BackfillPreview; busy: boolean; onStart: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  return <div className="prepared-card form-stack"><h3 tabIndex={-1} ref={heading}>Backfill request preview</h3>
    <p>{prepared.selected_count} of {prepared.eligible_count} unrequested excerpts · {prepared.batch_count} batches · {prepared.request_count} model requests</p>
    <p className="subtle">{prepared.covered_count} previously requested excerpts skipped. Processing stops at this limit; it will not automatically continue through the rest of your history.</p>
    {prepared.batches.map((batch, index) => <details key={index}><summary>Batch {index + 1} · {batch.source_count} excerpts · inspect inputs</summary>{batch.jobs.map((job, profile) => <div className="authoring-history" key={profile}><strong>{job.profile_name}</strong><p className="subtle">{job.model} · about {job.estimated_input_tokens.toLocaleString()} input tokens · instructions v{job.prompt_version}</p><pre className="authoring-prose" tabIndex={0}>{job.instructions}</pre><pre className="authoring-prose" tabIndex={0}>{job.content}</pre></div>)}</details>)}
    <button className="button primary" disabled={busy || !prepared.request_count} onClick={onStart}>Queue {prepared.request_count} model requests</button>
  </div>
}
