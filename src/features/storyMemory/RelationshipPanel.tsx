import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'

interface JobSummary { id: string; status: string; mode: string; error: string; usage: { calls?: number; seconds?: number }; created_at: string }
interface Status { eligible: number; prepared: number; annotations: number; available: boolean; reason: string; background: { verified: boolean; reason: string } | null; jobs: JobSummary[] }
interface Annotation { kind: string; relation: string; actor: string; description: string; evidence: { source_id: string; quote: string; start: number; end: number; sha256: string }[] }
interface Job extends JobSummary { output: string; result: { items: Annotation[] } | null; snapshot: { content: string } }

export function RelationshipPanel({ branch }: { branch: Branch }) {
  const action = useAction()
  const query = useQuery({ queryKey: ['relationships', branch.id], queryFn: () => api<Status>(`/branches/${branch.id}/relationships`), refetchInterval: 1500 })
  const prepare = () => action.run(async () => {
    await api(`/branches/${branch.id}/relationships`, { expected_revision: branch.revision, operation_id: operationId() })
    await query.refetch()
  })
  const status = query.data
  return <section className="form-stack"><h3>Tentative relationship links</h3>
    <p>Find promises, handoffs, outcomes and conflicting accounts in exact earlier prose. These are model interpretations used only to find originals. A quoted statement does not establish its truth or another character’s knowledge. Reviewing each link is optional.</p>
    <p className="subtle">Enable Use tentative relationship links in Story setup → Writing preferences. Check earlier evidence before writing uses available links. Preparation uses this Story’s writer profile and makes up to four requests for previously unrequested passages. Failed and stopped requests stay available for explicit retry.</p>
    <ErrorNotice message={query.error?.message || action.error || status?.reason} />
    {status && <><p>{status.annotations} source-backed annotation(s) currently eligible · {status.prepared} of {status.eligible} permitted passages previously requested.</p>
      <BackgroundStatus capability={status.background} />
      <button className="button" disabled={!status.available || action.busy || status.prepared >= status.eligible} onClick={prepare}>{action.busy ? 'Preparing…' : 'Prepare up to four missing passages'}</button>
      <div className="form-stack">{status.jobs.map(job => <RelationshipJob key={job.id} job={job} refresh={() => { void query.refetch() }} />)}</div>
    </>}
  </section>
}

function BackgroundStatus({ capability }: { capability: Status['background'] }) {
  return capability && <p className="subtle">Automatic preparation: {capability.verified ? 'interruption verified' : capability.reason}</p>
}

function RelationshipJob({ job, refresh }: { job: JobSummary; refresh: () => void }) {
  const [open, setOpen] = useState(false)
  const action = useAction()
  const query = useQuery({ queryKey: ['relationship-job', job.id, job.status], queryFn: () => api<Job>('/relationship-jobs/' + job.id), enabled: open })
  const active = ['queued', 'running'].includes(job.status)
  const retryable = ['error', 'cancelled', 'interrupted'].includes(job.status)
  const act = (operation: string) => action.run(async () => { await api(`/relationship-jobs/${job.id}/${operation}`, {}); refresh() })
  return <details className="request-details recall-receipt" open={open} onToggle={event => setOpen(event.currentTarget.open)}><summary>Relationship preparation · {job.status} · {new Date(job.created_at).toLocaleString()}</summary>
    <p>{job.mode} · {job.usage.calls ?? 0} request(s){job.usage.seconds !== undefined && ` · ${job.usage.seconds.toFixed(1)}s`}</p>
    <ErrorNotice message={job.error || query.error?.message || action.error} />
    {active && <button className="button" disabled={action.busy} onClick={() => act('cancel')}>Stop preparation</button>}
    {retryable && <button className="button" disabled={action.busy} onClick={() => act('retry')}>Retry this preparation</button>}
    {query.data && <AnnotationDetails job={query.data} />}
  </details>
}

function AnnotationDetails({ job }: { job: Job }) {
  return <div className="form-stack">{job.result?.items.map((item, index) => <div key={index} className="prepared-card"><p><strong>{item.kind} · {item.relation}</strong> · {item.actor}</p><p>{item.description}</p>
    {item.evidence.map((source, ordinal) => <blockquote key={ordinal}><p>{source.quote}</p><small>Exact source span {source.start}–{source.end}</small></blockquote>)}
  </div>)}<details><summary>Exact extraction inputs</summary><pre>{job.snapshot.content}</pre></details><details><summary>Original model response</summary><pre>{job.output}</pre></details></div>
}
