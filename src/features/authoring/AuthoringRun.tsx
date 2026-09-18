import { UsageSummary } from '../../components/UsageSummary'
import { useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { ownsRun, proseTargets, replaceProse } from './targets'
import { working, type EditorProps, type FrozenContent, type Job, type Run } from './types'

export function AuthoringRun({ runId, onNew, ...editor }: EditorProps & { runId: string; onNew: () => void }) {
  const query = useQuery({ queryKey: ['authoring-run', runId], queryFn: () => api<Run>(`/authoring/${runId}`), refetchInterval: (state) => state.state.data?.jobs.some(working) ? 700 : false })
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  return <section className="form-stack"><div className="section-heading"><h3 ref={heading} tabIndex={-1}>Review assistant suggestions</h3><button className="text-button" onClick={onNew}>New request</button></div>
    <ErrorNotice message={query.error?.message} />{query.data ? <RunResults {...editor} run={query.data} /> : <Loading />}
  </section>
}

function RunResults({ run, ...editor }: EditorProps & { run: Run }) {
  const [selected, setSelected] = useState(run.jobs[0]?.id)
  const job = run.jobs.find((item) => item.id === selected) ?? run.jobs[0]
  const source: FrozenContent = JSON.parse(run.snapshot.content)
  const compatible = ownsRun(run, editor)
  return <><p className="subtle">{run.snapshot.name || 'Untitled draft'} · {source.target.label} · {new Date(run.created_at).toLocaleString()}</p>
    <div className="authoring-alternatives" role="group" aria-label="Model alternatives">{run.jobs.map((item) => <button key={item.id} className={`button ${item.id === job?.id ? 'selected' : ''}`} aria-pressed={item.id === job?.id} onClick={() => setSelected(item.id)}>{item.snapshot.profile.name} · {item.status}</button>)}</div>
    {!compatible && <p className="subtle">This run belongs to another Library item. Its saved text can be reviewed here.</p>}
    {job && <JobResult key={job.id} {...editor} job={job} source={source} compatible={compatible} />}
  </>
}

function JobResult({ job, source, compatible, ...editor }: EditorProps & { job: Job; source: FrozenContent; compatible: boolean }) {
  const action = useAction()
  const request = (verb: string) => action.run(async () => { await api(`/authoring-jobs/${job.id}/${verb}`, {}) })
  const [inspect, setInspect] = useState(false)
  return <section className="form-stack" aria-label="Selected assistant result"><p className="subtle">{job.snapshot.profile.config.model} · instructions v{job.snapshot.prompt.number} · attempt {job.attempt}</p>
    {working(job) && <><p role="status">{job.status === 'queued' ? 'Waiting to start…' : 'The assistant is working…'} Closing this dialog keeps the request running.</p><button className="button" disabled={action.busy} onClick={() => request('stop')}>Stop assistant request</button></>}
    <ErrorNotice message={action.error || job.error} />
    {['error', 'interrupted', 'cancelled'].includes(job.status) && <button className="button" disabled={action.busy} onClick={() => request('retry')}>Retry saved request</button>}
    {job.status === 'done' && job.result && <><p className="authoring-summary">{job.result.summary}</p><ProposalReview {...editor} source={source} proposal={job.result.proposal} compatible={compatible} />
      {job.result.findings.map((finding, index) => <article className="prepared-card" key={index}><blockquote className="authoring-quote">{finding.quote}</blockquote><p>{finding.explanation}</p><p className="subtle">{finding.suggestion}</p></article>)}
    </>}
    <details open={inspect} onToggle={(event) => setInspect(event.currentTarget.open)}><summary>Saved request, raw output & attempts</summary>{inspect && <div className="form-stack authoring-history"><pre className="authoring-prose">{job.snapshot.prompt.template}</pre><pre className="authoring-prose">{job.snapshot.content}</pre><pre className="authoring-prose">{job.output || '(No output yet)'}</pre><UsageSummary usage={job.usage} /><Attempts jobId={job.id} attempt={job.attempt} /></div>}</details>
  </section>
}

function ProposalReview({ draft, onChange, source, proposal, compatible }: EditorProps & { source: FrozenContent; proposal: string | null; compatible: boolean }) {
  const [error, setError] = useState('')
  const target = proseTargets(draft).find((item) => item.key === source.target.key)
  const { applied, matches } = proposalState(target?.text, source.target.text, proposal)
  const apply = () => {
    if (proposal === null || !compatible) return
    try { onChange(replaceProse(draft, source.target.key, applied ? proposal : source.target.text, applied ? source.target.text : proposal)); setError('') }
    catch (failure) { setError(String(failure)) }
  }
  return <><ProseComparison original={source.target.text} proposal={proposal} />
    {proposal !== null && compatible && <div className="form-stack"><p className="subtle" role="status">{applied ? 'This unpublished draft matches the suggestion. Save a new Library version when you are ready, or restore the reviewed original.' : 'Review the complete replacement before applying it.'}</p>
      {!matches && <p className="subtle">The current field differs from the expected text. Your later edits are preserved; start a new request to use them.</p>}
      <button className={`button ${applied ? '' : 'primary'}`} disabled={!matches} onClick={apply}>{applied ? 'Restore reviewed original' : 'Apply to unpublished draft'}</button><ErrorNotice message={error} />
    </div>}
  </>
}

function proposalState(current: string | undefined, original: string, proposal: string | null) {
  const applied = proposal !== original && current === proposal
  return { applied, matches: current === (applied ? proposal : original) }
}

function ProseComparison({ original, proposal }: { original: string; proposal: string | null }) {
  return <div className="authoring-comparison"><section><h4>Reviewed original</h4><pre className="authoring-prose">{original || '(Empty passage)'}</pre></section>{proposal !== null && <section><h4>Suggested prose</h4><pre className="authoring-prose">{proposal}</pre></section>}</div>
}

function Attempts({ jobId, attempt }: { jobId: string; attempt: number }) {
  const query = useQuery({ queryKey: ['authoring-attempts', jobId, attempt], queryFn: () => api<{ id: string; status: string; output: string; error: string; attempt: number }[]>(`/authoring-jobs/${jobId}/attempts`) })
  return <><ErrorNotice message={query.error?.message} />{query.data?.map((item) => <details key={item.id}><summary>Attempt {item.attempt} · {item.status}</summary><p className="subtle">{item.error}</p><pre className="authoring-prose">{item.output || '(No output)'}</pre></details>)}</>
}
