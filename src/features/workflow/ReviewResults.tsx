import { useEffect, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { SourceMemoryCoverage, SourceMemoryDetails } from './SourceMemoryCoverage'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import { reviewRoleName } from './reviewNames'
import { working, type ReviewJob, type ReviewRun, type WorkflowStep } from './types'

function useReview(id: string) {
  const cache = useQueryClient()
  const query = useQuery({ queryKey: ['review', id], queryFn: () => api<ReviewRun>(`/reviews/${id}`), refetchInterval: (current) => current.state.data?.jobs.some(working) ? 1500 : false })
  const active = query.data?.jobs.some(working) ?? false
  useEffect(() => {
    if (!active) return
    const stream = new EventSource(`/api/reviews/${id}/events`)
    stream.onmessage = (event) => { try { cache.setQueryData(['review', id], JSON.parse(event.data)) } catch { stream.close() } }
    return () => stream.close()
  }, [active, id, cache])
  return query
}

function keepReportVisible(strip: HTMLDivElement) {
  const active = strip.querySelector<HTMLButtonElement>('[aria-pressed="true"]')
  if (!active) return
  const left = active.getBoundingClientRect().left - strip.getBoundingClientRect().left
  const right = left + active.offsetWidth - strip.clientWidth
  if (left < 4) strip.scrollLeft += left - 4
  else if (right > -4) strip.scrollLeft += right + 4
}

function ReportTabs({ run, selected, steps, onSelect }: { run: ReviewRun; selected?: string; steps: WorkflowStep[]; onSelect: (id: string) => void }) {
  const strip = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const node = strip.current
    if (!node) return
    const observer = new ResizeObserver(() => keepReportVisible(node))
    observer.observe(node)
    keepReportVisible(node)
    return () => observer.disconnect()
  }, [selected])
  return <div ref={strip} className="review-job-tabs" aria-label="Specialist reports">{run.jobs.map((job) => <button key={job.id} aria-pressed={selected === job.id} onClick={() => onSelect(job.id)}><strong>{reviewRoleName(steps, job.step)}</strong><span>{job.snapshot.profile.name}</span><small>{job.status}{run.selections[job.step] === job.id ? ' · preferred' : ''}</small></button>)}</div>
}

export function ReviewResults({ id, branch, steps }: { id: string; branch: Branch; steps: WorkflowStep[] }) {
  const query = useReview(id)
  const [selected, setSelected] = useState('')
  const current = query.data?.jobs.find((job) => job.id === selected) ?? query.data?.jobs[0]
  if (query.isPending) return <Loading label="Opening the review…" />
  return <div className="form-stack"><ErrorNotice message={query.error?.message} />{query.data && <>
    <ReviewHeading run={query.data} branch={branch} />
    <ReportTabs run={query.data} selected={current?.id} steps={steps} onSelect={setSelected} />
    {current && <ReviewReport key={current.id} job={current} run={query.data} />}
  </>}</div>
}

function ReviewHeading({ run, branch }: { run: ReviewRun; branch: Branch }) {
  const scene = run.snapshot.scene
  return <div><h3>{scene ? `${scene.title} · draft review` : `${run.snapshot.branch.name} · revision ${run.snapshot.branch.revision}`}</h3><p className="subtle">{scene ? `Proposed scene at plan revision ${scene.revision}; it has not been added to Story history.` : `${run.snapshot.draft_messages} contributions reviewed.`} These reports cannot change story text, canon or rolls.</p>
    {scene && <p role="status" className="scene-notice">{run.current_scene_draft ? 'These reports refer to the currently selected scene draft and plan.' : 'The scene or Story has changed. These earlier reports keep their original draft and sources.'}</p>}
    {!scene && run.snapshot.branch.revision !== branch.revision && <p className="subtle">The visible story has changed since this review began.</p>}
  </div>
}

function useReportFocus(status: string, busy: boolean) {
  const panel = useRef<HTMLElement>(null)
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const active = document.activeElement
      if (active === document.body || active?.getAttribute('role') === 'dialog') panel.current?.focus({ preventScroll: true })
    })
    return () => cancelAnimationFrame(frame)
  }, [status, busy])
  return panel
}

function ReviewReport({ job, run }: { job: ReviewJob; run: ReviewRun }) {
  const action = useAction()
  const panel = useReportFocus(job.status, action.busy)
  const control = (kind: 'cancel' | 'retry') => action.run(async () => { await api(`/review-jobs/${job.id}/${kind}`, {}) })
  const select = () => action.run(async () => { await api(`/reviews/${run.id}/selection`, { job_id: job.id }, 'PUT') })
  return <section ref={panel} tabIndex={-1} aria-label={`Review from ${job.snapshot.profile.name}`} className="review-report form-stack"><div className="candidate-meta"><span>{job.snapshot.profile.config.model} · prompt v{job.snapshot.prompt.number}</span><span role="status">{job.status} · attempt {job.attempt}</span></div>
    <ErrorNotice message={action.error || job.error} />
    <SourceMemoryCoverage memory={job.snapshot.source_memory} />
    {job.result && <><p className="review-summary">{job.result.summary}</p><ReviewCoverage job={job} /><ReviewFindings job={job} />{!job.result.findings.length && <p className="subtle">No findings were reported for the supplied material.</p>}<button className="button" disabled={action.busy || run.selections[job.step] === job.id} onClick={select}>{run.selections[job.step] === job.id ? 'Preferred report saved' : 'Mark preferred report'}</button><p className="subtle">This marks a comparison preference only. It does not apply any suggestion.</p></>}
    {working(job) && <><p className="subtle">The review runs independently. You can close this view and return to it later.</p><button className="button" disabled={action.busy} onClick={() => control('cancel')}>Stop this reviewer</button></>}
    {!working(job) && job.status !== 'done' && <button className="button" disabled={action.busy} onClick={() => control('retry')}>Retry original review inputs</button>}
    <details className="input-inspector"><summary>Inspect this review's exact sources, prompt and raw output</summary><p className="subtle">This may include attached Canon for privileged review roles. Estimated input: {job.snapshot.estimated_input_tokens.toLocaleString()} tokens.</p><h4>Role prompt</h4><pre>{job.snapshot.prompt.template}</pre><h4>Allowed sources</h4><pre>{JSON.stringify(JSON.parse(job.snapshot.content), null, 2)}</pre><SourceMemoryDetails memory={job.snapshot.source_memory} /><h4>Raw output</h4><pre>{job.output || 'No text returned yet.'}</pre><h4>Reported usage</h4><pre>{JSON.stringify(job.usage, null, 2)}</pre></details>
    <ReviewAttempts job={job} />
  </section>
}

function ReviewAttempts({ job }: { job: ReviewJob }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['review-attempts', job.id, job.attempt, job.status], queryFn: () => api<{ attempt: number; status: string; output: string; error: string }[]>(`/review-jobs/${job.id}/attempts`), enabled: open })
  if (job.attempt < 2) return null
  return <details className="input-inspector" onToggle={(event) => setOpen(event.currentTarget.open)}><summary>Preserved attempts</summary><ErrorNotice message={query.error?.message} />{query.data?.map((attempt) => <div key={attempt.attempt}><h4>Attempt {attempt.attempt} · {attempt.status}</h4><p>{attempt.error}</p><pre>{attempt.output || 'No text returned.'}</pre></div>)}</details>
}

function ReviewFindings({ job }: { job: ReviewJob }) {
  return job.result?.findings.map((finding, index) => <article className="review-finding" key={index}><span className={`finding-severity severity-${finding.severity}`}>{finding.lens && `${finding.lens} · `}{finding.severity}</span><blockquote>{finding.quote}</blockquote><p>{finding.explanation}</p><p><strong>Suggestion:</strong> {finding.suggestion}</p><small>Source: {finding.source_id}</small></article>)
}

function ReviewCoverage({ job }: { job: ReviewJob }) {
  if (!job.result?.coverage) return null
  return <section className="form-stack"><h4>Approved beat coverage</h4>{job.result.coverage.map(beat => <article className="review-finding" key={beat.beat_id}><h5>{beat.beat_id} · {beat.status}</h5><p>{beat.explanation}</p>{beat.quotes.map((quote, index) => <blockquote key={index}>{quote}</blockquote>)}</article>)}</section>
}
