import { useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { TextField } from '../../components/Fields'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import { working, type Source, type SummaryItem, type SummaryJob, type SummaryRun, type SummaryVersion } from './types'

interface Props { branch: Branch; runId: string; onNew: () => void }

export function SummaryResults({ branch, runId, onNew }: Props) {
  const query = useQuery({ queryKey: ['summary-run', runId, branch.id], queryFn: () => api<SummaryRun>('/summaries/' + runId + '?branch_id=' + branch.id), refetchInterval: state => state.state.data?.jobs.some(working) ? 700 : false })
  const [selected, setSelected] = useState('')
  const [restoring, setRestoring] = useState<SummaryVersion | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  const run = query.data
  const job = run?.jobs.find(item => item.id === (selected || run.current_version?.job_id)) ?? run?.jobs[0]
  const choose = (id: string) => { setSelected(id); setRestoring(null) }
  const restore = (version: SummaryVersion) => { setSelected(version.job_id); setRestoring(version) }
  return <section className="form-stack"><div className="section-heading"><h3 ref={heading} tabIndex={-1}>Review Story summaries</h3><button className="text-button" onClick={onNew}>New summary request</button></div>
    <ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}
    <div className="authoring-alternatives" role="group" aria-label="Summary alternatives">{run?.jobs.map(item => <button className="button" key={item.id} aria-pressed={item.id === job?.id} onClick={() => choose(item.id)}>{item.snapshot.profile.name} · {item.status}</button>)}</div>
    {run && job && <SummaryJobView key={job.id} job={job} run={run} branch={branch} restoring={restoring} />}
    {run && <VersionHistory run={run} onRestore={restore} />}
  </section>
}

function SummaryJobView({ job, run, branch, restoring }: { job: SummaryJob; run: SummaryRun; branch: Branch; restoring: SummaryVersion | null }) {
  const action = useAction()
  const command = (verb: string) => action.run(async () => { await api('/summary-jobs/' + job.id + '/' + verb, {}) })
  const initial = startingVersion(job, run, restoring)
  return <div className="form-stack"><p className="subtle">{job.snapshot.profile.config.model} · instructions v{job.snapshot.prompt.number} · attempt {job.attempt}</p>
    {working(job) && <><p role="status">Preparing summary suggestions. Closing keeps this request running.</p><button className="button" disabled={action.busy} onClick={() => command('stop')}>Stop summary request</button></>}
    {['error', 'cancelled', 'interrupted'].includes(job.status) && <button className="button" disabled={action.busy} onClick={() => command('retry')}>Retry saved summary request</button>}
    <ErrorNotice message={job.error || action.error} />
    {job.status === 'done' && job.result && <SummaryEditor key={job.attempt + ':' + (restoring?.id ?? 'current')} job={job} run={run} branch={branch} initial={initial} />}
    <details><summary>Exact request, output & usage</summary><pre className="authoring-prose" tabIndex={0}>{job.snapshot.prompt.template}</pre><pre className="authoring-prose" tabIndex={0}>{job.snapshot.content}</pre><pre className="authoring-prose" tabIndex={0}>{job.output}</pre><p className="subtle">Reported usage: {JSON.stringify(job.usage)}</p><SummaryAttempts job={job} /></details>
  </div>
}

function SummaryEditor({ job, run, branch, initial }: { job: SummaryJob; run: SummaryRun; branch: Branch; initial: SummaryVersion | null }) {
  const [items, setItems] = useState(initial?.result.items ?? job.result!.items)
  const [chosen, setChosen] = useState(items.map(item => item.source_id))
  const [enabled, setEnabled] = useState(initial ? !!initial.enabled : true)
  const [expected, setExpected] = useState(run.current_version?.id ?? null)
  const [saved, setSaved] = useState(false)
  const action = useAction()
  const sources: Source[] = JSON.parse(job.snapshot.content).sources
  const edit = (index: number, item: SummaryItem) => { setSaved(false); setItems(items.map((old, position) => position === index ? item : old)) }
  const save = () => action.run(async () => {
    const current = await api<Branch>('/branches/' + branch.id)
    const result = await api<{ id: string }>('/summaries/' + run.id + '/versions', { operation_id: operationId(), branch_id: branch.id,
      expected_revision: current.revision, expected_version_id: expected, job_id: job.id, enabled,
      result: { items: items.filter(item => chosen.includes(item.source_id)).map(cleanItem) } })
    setExpected(result.id); setSaved(true)
  })
  const toggle = (id: string) => { setSaved(false); setChosen(chosen.includes(id) ? chosen.filter(value => value !== id) : [...chosen, id]) }
  return <><p className="subtle">Check claims, speakers and uncertainty against the original. Matching quotations verify the source, not the interpretation. Save only the aids you trust.</p>
    {items.map((item, index) => <SummaryCard key={item.source_id} item={item} source={sources.find(source => source.id === item.source_id)!} chosen={chosen.includes(item.source_id)} onToggle={() => toggle(item.source_id)} onChange={next => edit(index, next)} />)}
    {!items.length && <p>No useful summaries were proposed. Original prose remains searchable.</p>}
    <label className="check-row"><input type="checkbox" checked={enabled} onChange={event => { setEnabled(event.target.checked); setSaved(false) }} />Allow this reviewed version to assist recall on this path</label>
    <p className="subtle">Uncheck to save an exclusion. Every earlier version stays available. A saved decision is inherited only by paths containing its accepted sources and the point where you saved it.</p>
    <ErrorNotice message={action.error} /><button className="button primary" disabled={action.busy || saved} onClick={save}>Save reviewed memory version</button>
    {saved && <p role="status">Memory version saved. Your manuscript is unchanged.</p>}
  </>
}

function cleanItem(item: SummaryItem): SummaryItem {
  return { ...item, topics: item.topics.map(term => term.trim()).filter(Boolean), aliases: item.aliases.map(term => term.trim()).filter(Boolean) }
}

function SummaryCard({ item, source, chosen, onToggle, onChange }: { item: SummaryItem; source: Source; chosen: boolean; onToggle: () => void; onChange: (item: SummaryItem) => void }) {
  return <article className="prepared-card form-stack"><label className="check-row"><input type="checkbox" checked={chosen} onChange={onToggle} />Use aid for {source.title} · characters {source.start + 1}–{source.end}</label>
    <details><summary>Original evidence & exact quotations</summary><pre className="authoring-prose" tabIndex={0}>{source.text}</pre>{item.quotes.map((quote, index) => <blockquote className="authoring-quote" key={index}>{quote}</blockquote>)}<small className="source-path subtle">Source {source.node_id} · SHA-256 {source.sha256}</small></details>
    <TextField label="Memory summary" aria-label="Memory summary" rows={3} value={item.summary} maxLength={1000} onChange={event => onChange({ ...item, summary: event.target.value })} />
    <TextField label="Topics · one per line" aria-label="Topics · one per line" rows={2} value={item.topics.join('\n')} maxLength={807} onChange={event => onChange({ ...item, topics: event.target.value.split('\n') })} hint="Up to 8 terms, 100 characters each. Empty lines are ignored." />
    <TextField label="Aliases · one per line" aria-label="Aliases · one per line" rows={2} value={item.aliases.join('\n')} maxLength={807} onChange={event => onChange({ ...item, aliases: event.target.value.split('\n') })} />
  </article>
}

function VersionHistory({ run, onRestore }: { run: SummaryRun; onRestore: (version: SummaryVersion) => void }) {
  return <details><summary>Preserved memory versions ({run.versions.length})</summary><div className="form-stack authoring-history"><p className="subtle">Loading an earlier version creates a draft here. Save it as a new decision to restore it on this path.</p>
    {run.versions.map(version => <article className="prepared-card" key={version.id}><p>{version.enabled ? 'Recall allowed' : 'Excluded from recall'} · {new Date(version.created_at).toLocaleString()}{run.current_version?.id === version.id ? ' · current on this path' : ''}</p><pre className="authoring-prose" tabIndex={0}>{version.result.items.map(item => item.summary).join('\n\n')}</pre><button className="text-button" onClick={() => onRestore(version)}>Use this version as draft</button></article>)}
  </div></details>
}

function SummaryAttempts({ job }: { job: SummaryJob }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['summary-attempts', job.id, job.attempt], queryFn: () => api<{ id: string; attempt: number; status: string; output: string; error: string }[]>('/summary-jobs/' + job.id + '/attempts'), enabled: open })
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Preserved attempts</summary><ErrorNotice message={query.error?.message} />{query.data?.map(item => <div key={item.id}><p>Attempt {item.attempt} · {item.status}</p><p>{item.error}</p><pre className="authoring-prose" tabIndex={0}>{item.output}</pre></div>)}</details>
}


function startingVersion(job: SummaryJob, run: SummaryRun, restoring: SummaryVersion | null) {
  return restoring ?? (run.current_version?.job_id === job.id ? run.current_version : null)
}
