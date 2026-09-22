import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { BranchSummary } from '../../types'
import { BranchPicker } from './BranchPicker'
import type { OpenPassage, SearchMatch, SearchRequest, SearchResults } from './types'

export function BranchSearch({ storyId, branches, onOpen }: { storyId: string; branches: BranchSummary[]; onOpen: OpenPassage }) {
  const [text, setText] = useState('')
  const [archived, setArchived] = useState(false)
  const [removed, setRemoved] = useState(false)
  const [ids, setIds] = useState<string[]>([])
  const [request, setRequest] = useState<SearchRequest | null>(null)
  const search = useQuery({ queryKey: ['branch-search', storyId, request], queryFn: () => api<SearchResults>(`/stories/${storyId}/branch-search`, { ...request, limit: 20 }), enabled: !!request })
  const branchesById = new Map(branches.map(branch => [branch.id, branch]))
  const results = search.data
  const submit = () => {
    const next = { query: text.trim(), branch_ids: ids, include_archived: archived, include_removed: removed, offset: 0 }
    if (JSON.stringify(next) === JSON.stringify(request)) void search.refetch()
    else setRequest(next)
  }
  return <div className="branch-tool-content form-stack"><form className="form-stack" onSubmit={event => { event.preventDefault(); submit() }}><label className="field"><span>Search prose across tellings</span><input aria-label="Search Story passages" type="search" maxLength={200} required value={text} onChange={event => setText(event.target.value)} placeholder="A phrase, a name, an unfinished promise…" /></label><div className="branch-tool-actions"><label className="check-row"><input type="checkbox" checked={archived} onChange={event => setArchived(event.target.checked)} />Include archived tellings</label><label className="check-row"><input type="checkbox" checked={removed} onChange={event => setRemoved(event.target.checked)} />Include omitted passages</label></div>
    <details><summary>{ids.length ? `Search ${ids.length} selected tellings` : 'Search all tellings, or choose specific paths'}</summary><div className="branch-filter-list"><BranchPicker branches={branches.filter(branch => archived || !branch.curation?.archived)} excluded={ids} value="" onChange={id => { if (id && ids.length < 1000) setIds([...ids, id]) }} label="Add a telling to search" />{ids.map(id => <div key={id} className="branch-tool-actions"><span>{branchesById.get(id)?.name ?? 'Unavailable telling'}{branchesById.get(id)?.curation?.archived ? ' · archived' : ''}</span><button type="button" className="text-button" onClick={() => setIds(ids.filter(value => value !== id))}>Remove filter</button></div>)}{ids.length > 0 && <button type="button" className="text-button" onClick={() => setIds([])}>Search all tellings</button>}</div></details><button className="button primary" disabled={!text.trim() || search.isFetching}>Search passages</button></form>
    <ErrorNotice message={search.error?.message} />{search.isFetching && <Loading label="Searching source passages…" />}{results && request && !search.isFetching && <SearchResultsView results={results} request={request} onChange={setRequest} onOpen={onOpen} />}
  </div>
}

function SearchResultsView({ results, request, onChange, onOpen }: { results: SearchResults; request: SearchRequest; onChange: (request: SearchRequest) => void; onOpen: OpenPassage }) {
  return <><p className="subtle" role="status">{results.total} source groups for “{results.query}” across {results.searched_branches} tellings.{request.include_archived ? ' Includes archived tellings.' : ' Archived tellings excluded.'}{request.include_removed ? ' Includes omitted passages.' : ''}</p><p className="subtle">Shared passages appear once, with a link to each telling. Edited and omitted versions remain distinct. Browsing here does not add sources to your writer’s context.</p><div className="branch-search-results">{results.results.map(item => <SearchCard key={item.group_id} item={item} onOpen={onOpen} />)}</div>{!results.total && <p className="subtle">No matching passages in this scope. Try another phrase or include archived tellings.</p>}<div className="branch-tool-actions"><button className="button" disabled={!request.offset} onClick={() => onChange({ ...request, offset: Math.max(0, request.offset - 20) })}>Previous results</button><button className="button" disabled={results.next_offset === null} onClick={() => results.next_offset !== null && onChange({ ...request, offset: results.next_offset })}>Next results</button></div></>
}

function SearchCard({ item, onOpen }: { item: SearchMatch; onOpen: OpenPassage }) {
  const [limit, setLimit] = useState(10)
  return <article className="branch-search-card"><span className="eyebrow">{item.role} · {item.occurrences.length} tellings{item.removed ? ' · omitted text' : ''}</span><p className="comparison-prose">{item.truncated_before ? '…' : ''}{item.before}<mark>{item.match}</mark>{item.after}{item.truncated_after ? '…' : ''}</p><div className="search-occurrences">{item.occurrences.slice(0, limit).map(item => <button className="button" key={`${item.branch_id}:${item.node_id}`} onClick={() => onOpen(item.branch_id, item.node_id)}>{item.branch_name} · r{item.branch_revision}{item.archived ? ' · archived' : ''}{item.favorite ? ' · favorite' : ''}</button>)}</div>{item.occurrences.length > limit && <button className="text-button" onClick={() => setLimit(limit + 50)}>Show more tellings ({item.occurrences.length - limit} remaining)</button>}</article>
}
