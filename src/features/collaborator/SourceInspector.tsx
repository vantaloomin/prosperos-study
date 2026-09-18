import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { SideTurn } from './types'

interface SourceRange { id: string; title: string; authority: string; text: string; start: number; end: number; total_chars: number; has_more: boolean; recall_aid?: { version_id: string; chunk_id: string } }
interface SourcePage { results: SourceRange[]; offset: number; total: number; next_offset: number | null }

export function SourceInspector({ turn }: { turn: SideTurn }) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState('')
  const [search, setSearch] = useState({ query: '', offset: 0 })
  const params = new URLSearchParams({ query: search.query, offset: String(search.offset) })
  const query = useQuery({ queryKey: ['side-source-search', turn.id, search], queryFn: () => api<SourcePage>(`/side-turns/${turn.id}/source-search?${params}`), enabled: open })
  return <details className="side-sources" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>{turn.snapshot.retrieval ? 'Inspect permitted frozen sources' : 'Inspect frozen sources, including hidden lore'}</summary>
    {open && <><form className="form-stack" onSubmit={(event) => { event.preventDefault(); setSearch({ query: draft, offset: 0 }) }}>
      <label className="field"><span>Find a source passage</span><input value={draft} maxLength={1000} onChange={(event) => setDraft(event.target.value)} placeholder="A name, object or phrase…" /></label>
      <button className="button" type="submit" disabled={query.isFetching}>Search this archive</button>
    </form><p className="subtle">Searches only this question’s frozen sources. It makes no model calls. Search results are excerpts; open a source to read further.</p>
      <ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Searching the frozen archive…" />}
      {query.data && <><p role="status">{query.data.total ? `${query.data.offset + 1}–${query.data.offset + query.data.results.length} of ${query.data.total} matching sources` : 'No matching sources. Try another term or an empty search to browse.'}</p>
        {query.data.results.map((source) => <SourceExcerpt key={`${source.id}:${source.start}`} turnId={turn.id} source={source} />)}
        <div className="side-reply-actions"><button className="button quiet" disabled={query.isFetching || !search.offset} onClick={() => setSearch({ ...search, offset: Math.max(0, search.offset - 8) })}>Previous sources</button><button className="button quiet" disabled={query.isFetching || query.data.next_offset === null} onClick={() => setSearch({ ...search, offset: query.data!.next_offset! })}>Next sources</button></div>
      </>}
    </>}
  </details>
}

function SourceExcerpt({ turnId, source }: { turnId: string; source: SourceRange }) {
  const [open, setOpen] = useState(false)
  const [offset, setOffset] = useState(source.start)
  const params = new URLSearchParams({ source_id: source.id, offset: String(offset), length: '2400' })
  const query = useQuery({ queryKey: ['side-source-range', turnId, source.id, offset], queryFn: () => api<SourceRange>(`/side-turns/${turnId}/source?${params}`), enabled: open })
  const current = query.data
  return <details onToggle={(event) => setOpen(event.currentTarget.open)}><summary>{source.title}</summary><small>{source.authority}</small>{source.recall_aid && <p className="subtle">This source has a reviewed memory aid. Search uses its reviewed description; the passage below is original prose.</p>}
    <ErrorNotice message={query.error?.message} />{query.isPending && open && <Loading label="Opening the exact source…" />}
    {current && <><p className="subtle" role="status">Characters {current.start + 1}–{current.end} of {current.total_chars}</p><pre>{current.text}</pre>
      <div className="side-reply-actions"><button className="text-button" disabled={query.isFetching || !offset} onClick={() => setOffset(Math.max(0, offset - 2400))}>Earlier text</button><button className="text-button" disabled={query.isFetching || !current.has_more} onClick={() => setOffset(current.end)}>Read further</button></div><small>{source.id}</small></>}
  </details>
}

export function RequestInputs({ replyId, index }: { replyId: string; index: number }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['side-request-inputs', replyId, index], queryFn: () => api<{ prompt: string; content: string; content_sha256: string }>(`/side-replies/${replyId}/requests/${index}`), enabled: open })
  return <details onToggle={(event) => setOpen(event.currentTarget.open)}><summary>Exact inputs · request {index + 1}</summary>
    <ErrorNotice message={query.error?.message} />{query.data && <><p>Collaborator instructions</p><pre>{query.data.prompt}</pre><p>Prepared context</p><pre>{JSON.stringify(JSON.parse(query.data.content), null, 2)}</pre><small>Context SHA-256: {query.data.content_sha256}</small></>}
  </details>
}
