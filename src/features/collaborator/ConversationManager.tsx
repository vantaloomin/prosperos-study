import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import type { ConversationLocation, ConversationMatch, SideThread } from './types'
import './conversationManager.css'

interface ConversationResult extends SideThread { match: ConversationMatch | null }
interface SearchPage { total: number; results: ConversationResult[]; next_offset: number | null }
interface Props { storyId: string; selected: string; onChoose: (id: string, location: ConversationLocation | null) => void; onClose: () => void }

export function ConversationManager({ storyId, selected, onChoose, onClose }: Props) {
  const [text, setText] = useState('')
  const destination = useRef<ConversationLocation | null>(null)
  const [search, setSearch] = useState({ query: '', archived: false, offset: 0 })
  const result = useQuery({ queryKey: ['side-thread-search', storyId, search], queryFn: () => api<SearchPage>(`/stories/${storyId}/side-conversations/search?query=${encodeURIComponent(search.query)}&include_archived=${search.archived}&offset=${search.offset}&limit=15`) })
  return <Modal open title="Conversations beside the story" description="Find an earlier discussion, give it a useful name, or set it aside without losing its sources." onClose={onClose} focusOnClose={() => destination.current ? document.querySelector(`[data-side-turn="${CSS.escape(destination.current.turnId)}"]`) : null} wide><div className="dialog-body form-stack"><form className="conversation-search" onSubmit={event => { event.preventDefault(); if (text.trim() === search.query && search.offset === 0) void result.refetch(); else setSearch({ ...search, query: text.trim(), offset: 0 }) }}><label className="field"><span>Search conversation names and messages</span><input type="search" aria-label="Search Companion conversations" value={text} onChange={event => setText(event.target.value)} maxLength={200} /></label><button className="button" disabled={result.isFetching}>Search conversations</button></form><label className="check-row"><input type="checkbox" checked={search.archived} onChange={event => setSearch({ ...search, archived: event.target.checked, offset: 0 })} />Include archived conversations</label><ErrorNotice message={result.error?.message} />{result.isPending && <Loading label="Finding conversations…" />}
    {result.data && <><p className="subtle" role="status">{result.data.total} conversations{search.query ? ` matching “${search.query}”` : ''}</p><div className="conversation-results">{result.data.results.map(item => <ConversationCard key={`${item.id}:${item.curation?.revision}`} item={item} selected={selected === item.id} onChoose={location => { destination.current = location; onChoose(item.id, location); onClose() }} />)}</div><div className="conversation-actions"><button className="button" disabled={!search.offset} onClick={() => setSearch({ ...search, offset: Math.max(0, search.offset - 15) })}>Previous conversations</button><button className="button" disabled={result.data.next_offset === null} onClick={() => { if (result.data?.next_offset != null) setSearch({ ...search, offset: result.data.next_offset }) }}>Next conversations</button></div></>}
  </div></Modal>
}

function ConversationCard({ item, selected, onChoose }: { item: ConversationResult; selected: boolean; onChoose: (location: ConversationLocation | null) => void }) {
  const [name, setName] = useState(item.name)
  const state = item.curation ?? { archived: false, revision: 0 }
  const action = useAction()
  const cache = useQueryClient()
  const save = (archived: boolean, title: string) => action.run(async () => {
    await api(`/side-conversations/${item.id}/organization`, { operation_id: operationId(), expected_revision: state.revision, name: title, archived }, 'PUT')
  })
  return <article className="conversation-card form-stack"><span className="eyebrow">{state.archived ? 'Archived conversation' : 'Conversation'}{selected ? ' · currently open' : ''}</span><label className="field"><span>Conversation name</span><input aria-label={`Rename ${item.name}`} value={name} maxLength={120} onChange={event => setName(event.target.value)} /></label><div className="conversation-actions"><button className="button" disabled={action.busy || !name.trim() || name.trim() === item.name} onClick={() => void save(state.archived, name)}>Save name</button><button className="text-button" disabled={action.busy} onClick={() => void save(!state.archived, item.name)}>{state.archived ? 'Unarchive conversation' : 'Archive conversation'}</button></div><ErrorNotice message={action.error} />{action.error && <button className="text-button" onClick={() => void cache.invalidateQueries()}>Refresh conversation details</button>}<MatchPreview match={item.match} onChoose={onChoose} /></article>
}

function MatchPreview({ match, onChoose }: { match: ConversationMatch | null; onChoose: (location: ConversationLocation | null) => void }) {
  const location = match?.turn_id ? { turnId: match.turn_id, replyId: match.reply_id } : null
  return <>{match && <p className="conversation-match"><span className="subtle">Found in {match.kind}</span><br />{match.truncated_before ? '…' : ''}{match.before}<mark>{match.match}</mark>{match.after}{match.truncated_after ? '…' : ''}</p>}<button className="button" onClick={() => onChoose(location)}>{location ? 'Open matching message' : 'Open conversation'}</button></>
}
