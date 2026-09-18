import { useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { ModelChoices } from '../authoring/AuthoringModels'
import { readyProfiles } from '../models/profileReadiness'
import type { ProfileList } from '../models/types'
import { PromptEditor, type Prompt } from '../prompts/Prompts'
import type { Preview, SetupProps, Source, SourcePage } from './types'

export function SummarySetup({ branch, onStarted }: SetupProps) {
  const [page, setPage] = useState(0)
  const [selected, setSelected] = useState<Source[]>([])
  const [compare, setCompare] = useState(false)
  const [profiles, setProfiles] = useState<string[]>([])
  const [prepared, setPrepared] = useState<Preview | null>(null)
  const action = useAction()
  const models = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const sources = useQuery({ queryKey: ['summary-sources', branch.id, branch.revision, page], queryFn: () => api<SourcePage>('/branches/' + branch.id + '/summary-sources?offset=' + page * 12) })
  const change = (update: () => void) => { update(); setPrepared(null) }
  const toggle = (source: Source) => change(() => setSelected(selected.some(item => item.id === source.id) ? selected.filter(item => item.id !== source.id) : [...selected, source]))
  const request = { expected_revision: sources.data?.revision ?? branch.revision, source_ids: selected.map(item => item.id), profile_ids: profiles }
  const preview = () => action.run(async () => setPrepared(await api<Preview>('/branches/' + branch.id + '/summary-preview', request)))
  const start = () => action.run(async () => {
    if (!prepared) return
    const run = await api<{ id: string }>('/branches/' + branch.id + '/summaries', { ...request, preview_hash: prepared.preview_hash, operation_id: operationId() })
    onStarted(run.id)
  })
  const invalid = invalidRequest(selected.length, models.data, compare, profiles.length)
  return <section className="form-stack"><h3>Choose accepted passages</h3><p className="subtle">Choose up to eight excerpts for this request. Only their original text is sent to the summary model. Author notes, private background, unsaved drafts and other paths are excluded.</p>
    <ErrorNotice message={action.error} /><ErrorNotice message={models.error?.message} /><ErrorNotice message={sources.error?.message} />
    <SourceChoices report={sources.data} pending={sources.isPending} fetching={sources.isFetching} selected={selected} page={page} onPage={setPage} onToggle={toggle} />
    {models.data && <ModelChoices profiles={models.data.profiles} selected={profiles} compare={compare} onMode={next => change(() => { setCompare(next); setProfiles([]) })} onChange={next => change(() => setProfiles(next))} />}
    <SummaryInstructions storyId={branch.story_id} onChange={() => setPrepared(null)} />
    <p className="subtle">One model request per selected profile. Previewing is local. Saved summaries are used only after review and when you enable them.</p>
    {prepared ? <SummaryPreview prepared={prepared} busy={action.busy} onStart={start} onRefresh={preview} /> : <button className="button primary" disabled={action.busy || invalid} onClick={preview}>Preview summary requests</button>}
  </section>
}

function SummaryPreview({ prepared, busy, onStart, onRefresh }: { prepared: Preview; busy: boolean; onStart: () => void; onRefresh: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  return <div className="prepared-card form-stack"><h3 tabIndex={-1} ref={heading}>Ready to summarize</h3><p>{prepared.request_count} model request(s) · {prepared.source_count} exact excerpts each</p>
    {prepared.jobs.map((job, index) => <div key={index}><strong>{job.profile_name}</strong><p className="subtle">{job.model} · about {job.estimated_input_tokens.toLocaleString()} input tokens · instructions v{job.prompt_version}</p><details><summary>Inspect exact inputs</summary><pre className="authoring-prose" tabIndex={0}>{job.instructions}</pre><pre className="authoring-prose" tabIndex={0}>{job.content}</pre></details></div>)}
    <button className="button" disabled={busy} onClick={onRefresh}>Refresh summary preview</button>
    <button className="button primary" disabled={busy} onClick={onStart}>Generate summary suggestions</button>
  </div>
}

function SummaryInstructions({ storyId, onChange }: { storyId: string; onChange: () => void }) {
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const action = useAction()
  const edit = () => action.run(async () => { const prompts = await api<Prompt[]>('/prompts?story_id=' + storyId); setPrompt(prompts.find(item => item.key === 'memory-summary') ?? null) })
  return <details className="advanced-settings"><summary>Summary instructions & model defaults</summary><div className="form-stack authoring-history"><p className="subtle">This action inherits the Primary Writer. Choose a permanent override for “Story memory summary” in this Story’s model routing, or choose a model above for this request.</p><button className="text-button" disabled={action.busy} onClick={edit}>Edit summary instructions for this Story</button><ErrorNotice message={action.error} />
    {prompt && <PromptEditor prompt={prompt} storyId={storyId} onClose={() => { setPrompt(null); onChange() }} />}
  </div></details>
}


function invalidRequest(count: number, models: ProfileList | undefined, compare: boolean, profiles: number) {
  return !count || !models?.profiles.length || (compare && (profiles < 2 || profiles > 4))
}

export function SourceChoices({ report, pending, fetching, selected, page, onPage, onToggle, emptyMessage = "No accepted prose yet. Write or accept a passage first." }: { report?: SourcePage; pending: boolean; fetching: boolean; selected: Source[]; page: number; onPage: (page: number) => void; onToggle: (source: Source) => void; emptyMessage?: string }) {
  return <>{pending && <Loading />}<p role="status">{selected.length} excerpts selected</p>
    {report?.items.map((source, index) => <article className="prepared-card" key={source.id}><label className="check-row"><input type="checkbox" checked={selected.some(item => item.id === source.id)} disabled={selected.length >= 8 && !selected.some(item => item.id === source.id)} onChange={() => onToggle(source)} />Excerpt {page * 12 + index + 1} · {source.name ?? source.title}{source.edition ? " · edition " + source.edition : ""}{source.field ? " · " + source.field : ""}</label><details><summary>Read original · characters {source.start + 1}–{source.end}</summary><pre className="authoring-prose" tabIndex={0}>{source.text}</pre></details></article>)}
    {report?.matches === 0 && <p>{emptyMessage}</p>}
    <div className="import-downloads"><button className="button" disabled={!page || fetching} onClick={() => onPage(page - 1)}>Previous excerpts</button><button className="button" disabled={!report?.next_offset || fetching} onClick={() => onPage(page + 1)}>Next excerpts</button></div>
  </>
}
