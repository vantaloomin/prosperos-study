import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { TextField } from '../../components/Fields'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import { analysisWorking, styleLabels, type AnalysisJob, type AnalysisListItem, type StyleField, type StylePatch } from './analysisTypes'
import type { StyleContent } from './types'

export function AnalysisResult({ job, current, onApply }: { job: AnalysisJob; current?: StyleContent; onApply?: (changes: StylePatch, expected: StylePatch) => void }) {
  const action = useAction()
  const control = (verb: 'stop' | 'retry') => action.run(async () => { await api(`/writing-analyses/${job.id}/${verb}`, {}) })
  return <section className="form-stack" aria-label="Saved sample analysis"><h3>{job.snapshot.name || 'Writing sample analysis'}</h3><p role="status">Analysis {job.status} · attempt {job.attempt} · {job.snapshot.profile.name}</p><ErrorNotice message={job.error || action.error} />
    {analysisWorking(job.status) && <button className="button" disabled={action.busy} onClick={() => control('stop')}>Stop analysis</button>}
    {['error', 'cancelled', 'interrupted'].includes(job.status) && <button className="button" disabled={action.busy} onClick={() => control('retry')}>Retry original analysis inputs</button>}
    <details><summary>Samples and exact analysis request</summary><AnalysisInputs snapshot={job.snapshot} /></details>
    {job.status === 'done' && job.result && <><p>{job.result.summary}</p><AnalysisSuggestions key={job.id} job={job} current={current} onApply={onApply} /></>}
    <details><summary>Original model output and earlier attempts</summary><pre className="authoring-prose" tabIndex={0}>{job.output || 'No response text yet.'}</pre><AnalysisAttempts id={job.id} attempt={job.attempt} /></details>
  </section>
}

export function AnalysisInputs({ snapshot }: { snapshot: AnalysisJob['snapshot'] }) {
  return <div className="form-stack">{snapshot.samples.map((sample, index) => <div key={index}><h4>sample:{index + 1} · {sample.label}</h4><pre className="authoring-prose" tabIndex={0}>{sample.text}</pre></div>)}<h4>Final instructions</h4><pre className="authoring-prose" tabIndex={0}>{snapshot.instructions}</pre><h4>Exact content</h4><pre className="authoring-prose" tabIndex={0}>{snapshot.content}</pre></div>
}

function AnalysisSuggestions({ job, current, onApply }: { job: AnalysisJob; current?: StyleContent; onApply?: (changes: StylePatch, expected: StylePatch) => void }) {
  const suggestions = job.result!.suggestions
  const [edited, setEdited] = usePersistent<StylePatch>(`prospero:style-analysis-edits:${job.id}`, Object.fromEntries(suggestions.map(item => [item.field, item.value])))
  const [selected, setSelected] = useState<StyleField[]>(suggestions.map(item => item.field))
  const [copied, setCopied] = useState(false)
  const action = useAction()
  const apply = () => action.run(async () => {
    if (!onApply || !current) return
    onApply(Object.fromEntries(selected.map(key => [key, edited[key] ?? ''])), Object.fromEntries(selected.map(key => [key, current[key]])))
    setCopied(true)
  })
  return <div className="form-stack">{!suggestions.length && <p>No supported style suggestions were returned. The profile is unchanged.</p>}{suggestions.map(item => <fieldset className="writing-sample form-stack" key={item.field}><legend>{styleLabels[item.field]}</legend>
    {onApply && <label className="check-row"><input type="checkbox" checked={selected.includes(item.field)} onChange={event => { setSelected(event.target.checked ? [...selected, item.field] : selected.filter(key => key !== item.field)); setCopied(false) }} />Use {styleLabels[item.field]}</label>}
    {current && <div><strong>Current draft wording</strong><pre className="authoring-prose">{current[item.field] || '(empty)'}</pre></div>}
    <TextField label={`Suggested ${styleLabels[item.field]}`} value={edited[item.field] ?? item.value} rows={3} maxLength={12000} onChange={event => { setEdited({ ...edited, [item.field]: event.target.value }); setCopied(false) }} />
    <p>{item.reason}</p>{item.evidence.map((source, index) => <blockquote key={index}><p>{source.quote}</p><cite>{source.sample_id} · {job.snapshot.samples[Number(source.sample_id.split(':')[1]) - 1]?.label}</cite></blockquote>)}
  </fieldset>)}<ErrorNotice message={action.error} />{onApply && !!suggestions.length && <><p className="subtle">Only the selected guidance fields will change. Samples and other draft fields stay as shown in the editor. Publishing remains a separate action.</p><button className="button primary" disabled={!selected.length || action.busy} onClick={apply}>Copy selected suggestions to draft</button>{copied && <p role="status">Suggestions copied to the draft. No profile was published.</p>}</>}</div>
}

function AnalysisAttempts({ id, attempt }: { id: string; attempt: number }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['style-analysis-attempts', id, attempt], queryFn: () => api<{ attempt: number; status: string; output: string; error: string }[]>(`/writing-analyses/${id}/attempts`), enabled: open })
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Saved attempts</summary><ErrorNotice message={query.error?.message} />{query.data?.map(item => <div key={item.attempt}><h4>Attempt {item.attempt} · {item.status}</h4><p>{item.error}</p><pre className="authoring-prose" tabIndex={0}>{item.output}</pre></div>)}</details>
}

export function AnalysisHistoryList({ onSelect }: { onSelect: (id: string) => void }) {
  const query = useQuery({ queryKey: ['style-analyses'], queryFn: () => api<AnalysisListItem[]>('/writing-analyses'), refetchInterval: 5000 })
  return <div className="form-stack"><ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Reading analyses…" />}{query.data?.length === 0 && <p>No saved sample analyses yet.</p>}{query.data?.map(item => <button key={item.id} className="button" onClick={() => onSelect(item.id)}>{item.name || 'Untitled writing style'} · {item.status} · {new Date(item.updated_at).toLocaleString()}</button>)}</div>
}
