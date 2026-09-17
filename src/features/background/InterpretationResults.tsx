import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { privateWorking, type PrivateJob, type PrivateRun } from './interpretationTypes'
import { PrivateContentView } from './PrivateContentView'

export function InterpretationResults({ id, onBranch }: { id: string; onBranch: (id: string) => void }) {
  const [reveal, setReveal] = useState(false)
  const query = useQuery({ queryKey: ['private-interpretation', id, reveal], queryFn: () => api<PrivateRun>(`/background-interpretations/${id}?reveal=${reveal}`), refetchInterval: (state) => state.state.data?.jobs.some(privateWorking) ? 700 : false })
  return <div className="form-stack">
    <div className="mechanics-footer"><p className="subtle">Choose by profile to keep a surprise, or reveal the alternatives before choosing. Keeping one changes private guidance only.</p><button className="button" onClick={() => setReveal(!reveal)}>{reveal ? 'Conceal alternatives' : 'Reveal alternatives'}</button></div>
    <ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Opening private alternatives…" />}{query.data && <>
    {query.data.stale && <p className="subtle">This request belongs to an earlier Story state. An unselected alternative can be kept on a new branch from its original point.</p>}
    {query.data.jobs.map((job) => <InterpretationJob key={job.id} job={job} stale={query.data.stale} reveal={reveal} onBranch={onBranch} />)}
  </>}</div>
}

function InterpretationJob({ job, stale, reveal, onBranch }: { job: PrivateJob; stale: boolean; reveal: boolean; onBranch: (id: string) => void }) {
  const action = useAction()
  const [fork, setFork] = useState(false)
  const request = (verb: string) => action.run(async () => { await api(`/background-jobs/${job.id}/${verb}`, {}) })
  const choose = () => action.run(async () => {
    const result = await api<{ branch_id: string }>(`/background-jobs/${job.id}/choose`, { operation_id: operationId(), as_new_branch: stale || fork })
    onBranch(result.branch_id)
  })
  return <section className="candidate-view form-stack"><div className="candidate-meta"><strong>{job.profile_name}</strong><span role="status">{job.status} · attempt {job.attempt}</span></div><p className="subtle">{job.model} · prompt v{job.prompt_version}</p>
    <ErrorNotice message={job.error || action.error} />{reveal ? <RevealedJob job={job} /> : <p className="subtle">Private content is concealed.</p>}
    <PrivateJobActions job={job} stale={stale} fork={fork} onFork={setFork} busy={action.busy} onChoose={choose} onRequest={request} />
  </section>
}

function PrivateJobActions({ job, stale, fork, onFork, busy, onChoose, onRequest }: { job: PrivateJob; stale: boolean; fork: boolean; onFork: (value: boolean) => void; busy: boolean; onChoose: () => void; onRequest: (verb: string) => void }) {
  if (privateWorking(job)) return <button className="button" disabled={busy} onClick={() => onRequest('stop')}>Stop private interpretation</button>
  if (job.selected_state_id) return <button className="button" disabled={busy} onClick={onChoose}>Open chosen path</button>
  if (job.status !== 'done') return <button className="button" disabled={busy} onClick={() => onRequest('retry')}>Retry original private inputs</button>
  return <>{!stale && <label className="check-row"><input type="checkbox" checked={fork} onChange={(event) => onFork(event.target.checked)} />Keep this on a new branch</label>}<button className="button primary" disabled={busy} onClick={onChoose}>{stale || fork ? 'Keep on a new branch' : 'Use as private background'}</button></>
}

function RevealedJob({ job }: { job: PrivateJob }) {
  return <>{job.result && <PrivateContentView content={job.result} targets={job.targets} />}<details className="input-inspector"><summary>Exact private inputs, output & usage</summary><pre>{JSON.stringify({ prompt: job.snapshot?.prompt.template, content: job.snapshot?.content, output: job.output, usage: job.usage }, null, 2)}</pre></details><PrivateAttempts job={job} /></>
}

function PrivateAttempts({ job }: { job: PrivateJob }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['private-attempts', job.id, job.attempt], queryFn: () => api<unknown[]>(`/background-jobs/${job.id}/attempts/reveal`), enabled: open })
  if (job.attempt < 2) return null
  return <><button className="text-button" onClick={() => setOpen(!open)}>{open ? 'Hide' : 'Reveal'} earlier attempts</button>{open && <><ErrorNotice message={query.error?.message} /><pre className="raw-json">{JSON.stringify(query.data, null, 2)}</pre></>}</>
}
