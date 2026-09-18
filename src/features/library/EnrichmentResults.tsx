import { useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { TextField } from '../../components/Fields'
import { useAction } from '../../hooks/useAction'
import type { AssetContent } from '../../types'
import { working, type Job, type Run } from '../authoring/types'

export interface EnrichmentCue { source_id: string; summary: string; topics: string[]; aliases: string[] }
interface Props { content: AssetContent; runId: string; onChange: (patch: Partial<AssetContent>) => void; onNew: () => void }

export function EnrichmentResults(props: Props) {
  const query = useQuery({ queryKey: ['authoring-run', props.runId], queryFn: () => api<Run>('/authoring/' + props.runId), refetchInterval: state => state.state.data?.jobs.some(working) ? 700 : false })
  const heading = useRef<HTMLHeadingElement>(null)
  const [selected, setSelected] = useState('')
  useLayoutEffect(() => { heading.current?.focus() }, [])
  const job = query.data?.jobs.find(item => item.id === selected) ?? query.data?.jobs[0]
  return <section className="form-stack"><div className="section-heading"><h3 tabIndex={-1} ref={heading}>Review search aids</h3><button className="text-button" onClick={props.onNew}>New request</button></div>
    <ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}
    <div className="authoring-alternatives" role="group" aria-label="Search-aid alternatives">{query.data?.jobs.map(item => <button className="button" key={item.id} aria-pressed={item.id === job?.id} onClick={() => setSelected(item.id)}>{item.snapshot.profile.name} · {item.status}</button>)}</div>
    {job && <EnrichmentJob key={job.id} job={job} content={props.content} onChange={props.onChange} />}
  </section>
}

function EnrichmentJob({ job, content, onChange }: { job: Job; content: AssetContent; onChange: Props['onChange'] }) {
  const action = useAction()
  const command = (verb: string) => action.run(async () => { await api('/authoring-jobs/' + job.id + '/' + verb, {}) })
  return <div className="form-stack"><p className="subtle">{job.snapshot.profile.config.model} · instructions v{job.snapshot.prompt.number} · attempt {job.attempt}</p>
    {working(job) && <><p role="status">Preparing source-bound search aids. Closing keeps this request running.</p><button className="button" disabled={action.busy} onClick={() => command('stop')}>Stop search-aid request</button></>}
    {['error', 'cancelled', 'interrupted'].includes(job.status) && <button className="button" disabled={action.busy} onClick={() => command('retry')}>Retry saved request</button>}
    <ErrorNotice message={job.error || action.error} />
    {job.status === 'done' && job.result?.enrichment && <CueReview key={job.attempt} job={job} content={content} onChange={onChange} />}
    <details><summary>Exact inputs, output & usage</summary><pre className="authoring-prose" tabIndex={0}>{job.snapshot.prompt.template}</pre><pre className="authoring-prose" tabIndex={0}>{job.snapshot.content}</pre><pre className="authoring-prose" tabIndex={0}>{job.output}</pre><p className="subtle">Reported usage: {JSON.stringify(job.usage)}</p><Attempts job={job} /></details>
  </div>
}

function CueReview({ job, content, onChange }: { job: Job; content: AssetContent; onChange: Props['onChange'] }) {
  const [cues, setCues] = useState(job.result!.enrichment!)
  const [chosen, setChosen] = useState(cues.map(cue => cue.source_id))
  const [applied, setApplied] = useState(false)
  const action = useAction()
  const current = useRef({ content, onChange })
  useLayoutEffect(() => { current.current = { content, onChange } }, [content, onChange])
  const sources: { id: string; text: string; title: string }[] = JSON.parse(JSON.parse(job.snapshot.content).target.text)
  const apply = () => action.run(async () => {
    const before = current.current.content
    const patch = await api<Partial<AssetContent>>('/canon/enrichment-apply', { job_id: job.id, content: before, cues: cues.filter(cue => chosen.includes(cue.source_id)).map(cue => ({ ...cue, topics: cue.topics.map(term => term.trim()).filter(Boolean), aliases: cue.aliases.map(term => term.trim()).filter(Boolean) })) })
    if (JSON.stringify(current.current.content) !== JSON.stringify(before)) throw new Error('This draft changed while applying. Your later edits are preserved; try again with the current draft.')
    current.current.onChange(patch); setApplied(true)
  })
  const edit = (index: number, cue: EnrichmentCue) => setCues(cues.map((item, position) => position === index ? cue : item))
  return <><p>{job.result!.summary}</p><p className="subtle">Check uncertainty, names and implications against the original. A valid source link does not prove a summary is faithful. Only checked suggestions are added; existing cues are kept.</p>
    {cues.map((cue, index) => <article className="prepared-card form-stack" key={cue.source_id}><label className="check-row"><input type="checkbox" disabled={applied} checked={chosen.includes(cue.source_id)} onChange={() => setChosen(chosen.includes(cue.source_id) ? chosen.filter(id => id !== cue.source_id) : [...chosen, cue.source_id])} />Use aid for {sources.find(source => source.id === cue.source_id)?.title}</label>
      <details><summary>Original evidence</summary><pre className="authoring-prose" tabIndex={0}>{sources.find(source => source.id === cue.source_id)?.text}</pre></details>
      <TextField label="Retrieval summary" aria-label="Retrieval summary" rows={3} maxLength={1200} disabled={applied} value={cue.summary} onChange={event => edit(index, { ...cue, summary: event.target.value })} />
      <TermField label="Topics · one per line" values={cue.topics} disabled={applied} onChange={topics => edit(index, { ...cue, topics })} />
      <TermField label="Aliases · one per line" values={cue.aliases} disabled={applied} onChange={aliases => edit(index, { ...cue, aliases })} />
    </article>)}
    {!cues.length && <p className="subtle">No useful search aids were proposed. The original remains searchable.</p>}
    <ErrorNotice message={action.error} />{applied ? <p role="status">Added to your unpublished draft. Save a new Canon version when ready.</p> : <button className="button primary" disabled={action.busy || !chosen.length} onClick={apply}>Add selected aids to draft</button>}
  </>
}

function TermField({ label, values, disabled, onChange }: { label: string; values: string[]; disabled: boolean; onChange: (values: string[]) => void }) {
  return <TextField label={label} aria-label={label} rows={2} maxLength={1452} disabled={disabled} value={values.join('\n')} onChange={event => onChange(event.target.value.split('\n'))} hint="Up to 12 terms, 120 characters each. Empty lines are ignored when applying." />
}

function Attempts({ job }: { job: Job }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['authoring-attempts', job.id, job.attempt], queryFn: () => api<{ id: string; attempt: number; status: string; output: string; error: string }[]>('/authoring-jobs/' + job.id + '/attempts'), enabled: open })
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Preserved attempts</summary><ErrorNotice message={query.error?.message} />{query.data?.map(item => <div key={item.id}><p>Attempt {item.attempt} · {item.status}</p><p>{item.error}</p><pre className="authoring-prose">{item.output}</pre></div>)}</details>
}
