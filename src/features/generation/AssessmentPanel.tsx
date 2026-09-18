import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import type { Beat } from '../mechanics/types'
import { RollInspector } from '../mechanics/RollInspector'
import type { ReviewJob } from '../workflow/types'
import './assessment.css'

interface AssessmentJob extends Omit<ReviewJob, 'result'> {
  result: { summary: string; beat: Beat; evidence: { node_id: string; quote: string }[] } | null
}
interface Assessment {
  id: string; stale: boolean; stopped: number; error: string; generation_id: string | null
  opportunity_id: string | null; selected_job_id: string | null; jobs: AssessmentJob[]
  snapshot: { purpose?: string; branch: { id: string; name: string }; writer_profiles: { name: string }[] }
}
const working = (job: AssessmentJob) => ['queued', 'running'].includes(job.status)

function shouldPoll(run: Assessment | undefined) {
  if (!run) return true
  if (run.jobs.some(working)) return true
  if (run.snapshot.purpose === 'post-acceptance' && run.opportunity_id) return false
  return !run.generation_id && !run.error && !run.stopped && !run.stale && run.jobs.length === 1 && run.jobs[0].status === 'done'
}

export default function AssessmentPanel({ id, followWriter, onClose, onWriter, inline = false }: { id: string; followWriter: boolean; onClose: () => void; onWriter: (id: string) => void; inline?: boolean }) {
  const query = useQuery({ queryKey: ['assessment', id], queryFn: () => api<Assessment>(`/assessments/${id}`), refetchInterval: (state) => shouldPoll(state.state.data) ? 500 : false })
  const cache = useQueryClient()
  const followed = useRef(false)
  const run = query.data
  useEffect(() => {
    if (followWriter && run?.generation_id && !followed.current) {
      followed.current = true
      void cache.invalidateQueries({ queryKey: ['branch', run.snapshot.branch.id] })
      onWriter(run.generation_id)
    }
  }, [run, followWriter, onWriter, cache])
  const content = <div className="dialog-body form-stack"><ErrorNotice message={query.error?.message} />{!run && <Loading label="Opening beat assessment…" />}{run && <AssessmentContent run={run} onWriter={onWriter} />}</div>
  if (inline) return <section className="inline-draft" aria-label="Beat assessment"><header><h3>Beat assessment status</h3><button className="text-button" disabled={!run || run.jobs.some(working)} onClick={onClose}>Dismiss assessment</button></header>{content}</section>
  return <Modal open onClose={onClose} title="Before the next moment" description="Check whether the story has reached a natural opening for chance. Assessments do not advance the story." wide>{content}</Modal>
}

function AssessmentContent({ run, onWriter }: { run: Assessment; onWriter: (id: string) => void }) {
  const action = useAction()
  const decide = (jobId?: string) => action.run(async () => {
    const result = await api<{ id?: string }>(`/assessments/${run.id}/decision`, { operation_id: operationId(), job_id: jobId ?? null, without_chance: !jobId })
    if (result.id) onWriter(result.id)
  })
  const stop = () => action.run(async () => { await api(`/assessments/${run.id}/stop`, {}) })
  return <>{run.snapshot.purpose === 'post-acceptance' ? <p className="subtle">Scribe prepares the next beat from accepted text. Writing never waits for it, and this task cannot advance the Story.</p> : <p className="subtle">{run.snapshot.branch.name} · Assessment requests: {run.jobs.length}. Writer requests: {run.snapshot.writer_profiles.length}. {run.jobs.length > 1 ? 'Choose one report to continue.' : 'One validated report starts the saved writer request automatically.'}</p>}
    {run.stale && <p role="status" className="subtle">The Story changed. These inputs are preserved; return to the current branch to continue.</p>}
    {!!run.stopped && !run.generation_id && <p role="status">Assessment stopped. Writing can continue without this result.</p>}
    <ErrorNotice message={action.error || run.error} />
    {run.jobs.map((job) => <AssessmentReport key={job.id} job={job} run={run} busy={action.busy} onChoose={() => void decide(job.id)} />)}
    {run.jobs.some(working) && <button className="button" disabled={action.busy} onClick={stop}>Stop beat assessment</button>}
    <AssessmentContinuation run={run} busy={action.busy} onWriter={onWriter} onSkip={() => void decide()} />
    <AssessmentChance id={run.opportunity_id} />
  </>
}

function AssessmentChance({ id }: { id: string | null }) {
  const [open, setOpen] = useState(false)
  if (!id) return null
  return <><button className="text-button" onClick={() => setOpen(true)}>Inspect saved chance</button>{open && <RollInspector id={id} onClose={() => setOpen(false)} />}</>
}

function AssessmentContinuation({ run, busy, onWriter, onSkip }: { run: Assessment; busy: boolean; onWriter: (id: string) => void; onSkip: () => void }) {
  if (run.snapshot.purpose === 'post-acceptance') return <p role="status">{run.opportunity_id && !run.stale && !run.stopped ? 'Beat prepared. It is available to the next writing request at this exact point.' : 'Return to the composer to write without waiting for an assessment.'}</p>
  if (run.generation_id) return <button className="button primary" onClick={() => onWriter(run.generation_id!)}>Open saved drafts</button>
  return <button className="text-button" disabled={run.stale || busy} onClick={onSkip}>Continue without chance for this request</button>
}

function AssessmentReport({ job, run, busy, onChoose }: { job: AssessmentJob; run: Assessment; busy: boolean; onChoose: () => void }) {
  const action = useAction()
  const retry = () => action.run(async () => { await api(`/assessment-jobs/${job.id}/retry`, {}) })
  return <section className="candidate-view assessment-report"><div className="candidate-meta"><strong>{job.snapshot.profile.name}</strong><span role="status">{job.status} · attempt {job.attempt}</span></div>
    {job.result ? <><p>{job.result.summary}</p><p className="subtle">{eligibility(job.result.beat)}</p>{job.result.evidence.map((item, index) => <blockquote key={index}>{item.quote}</blockquote>)}</> : <p className="subtle">{working(job) ? 'Checking the accepted story and player agency…' : 'No validated assessment. Your story is unchanged.'}</p>}
    <ErrorNotice message={job.error || action.error} />
    {!run.generation_id && !run.opportunity_id && !run.stale && <AssessmentJobAction post={run.snapshot.purpose === 'post-acceptance'} job={job} busy={busy || action.busy} onChoose={onChoose} onRetry={() => void retry()} />}
    {run.selected_job_id === job.id && <p className="subtle">Selected for the saved chance result.</p>}
    <details><summary>Original inputs, output & usage</summary><p className="subtle">{job.snapshot.profile.config.model} · prompt v{job.snapshot.prompt.number} · estimated input {job.snapshot.estimated_input_tokens.toLocaleString()} tokens</p><pre className="raw-json">{JSON.stringify({ prompt: job.snapshot.prompt.template, content: job.snapshot.content, output: job.output, usage: job.usage }, null, 2)}</pre><AssessmentAttempts id={job.id} attempt={job.attempt} /></details>
  </section>
}

function AssessmentJobAction({ post, job, busy, onChoose, onRetry }: { post: boolean; job: AssessmentJob; busy: boolean; onChoose: () => void; onRetry: () => void }) {
  if (job.status === 'done') return <button className="button primary" disabled={busy} onClick={onChoose}>{post ? 'Prepare this beat' : 'Use this assessment & write'}</button>
  if (working(job)) return null
  return <button className="button" disabled={busy} onClick={onRetry}>Retry original assessment inputs</button>
}

function AssessmentAttempts({ id, attempt }: { id: string; attempt: number }) {
  const query = useQuery({ queryKey: ['assessment-attempts', id, attempt], queryFn: () => api<unknown[]>(`/assessment-jobs/${id}/attempts`), enabled: attempt > 1 })
  if (attempt < 2) return null
  return <details><summary>Earlier attempts</summary><ErrorNotice message={query.error?.message} /><pre className="raw-json">{JSON.stringify(query.data, null, 2)}</pre></details>
}

function eligibility(beat: Beat) {
  if (!beat.completed) return 'The beat is still in progress; no draw.'
  if (beat.waiting_for_player) return 'Waiting for the player; no draw.'
  if (beat.protected) return 'This moment is protected; no draw.'
  return 'Eligible for enabled mechanics, subject to cooldown and unresolved events.'
}
