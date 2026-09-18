import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import { CharacterBinding, ControlSources, type CharacterIdentity } from './ControlSources'
import type { Source } from './types'
import { labels, states, type Entry } from './controlTypes'

export function ControlEditor({ branch, characters, entry, onChange, onKeep, onCancel }: { branch: Branch; characters: CharacterIdentity[]; entry: Entry; onChange: (entry: Entry) => void; onKeep: (entry: Entry) => void; onCancel: () => void }) {
  const inputId = useId()
  const setEntry = onChange
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  const toggle = (source: Source) => setEntry({ ...entry, sources: entry.sources.some(item => item.id === source.id) ? entry.sources.filter(item => item.id !== source.id) : [...entry.sources, source] })
  const valid = entry.subject.trim() && entry.text.trim() && entry.sources.length >= (entry.kind === 'conflict' ? 2 : 1)
  return <div className="form-stack"><h4 tabIndex={-1} ref={heading}>{labels[entry.kind]}</h4>
    {entry.kind === 'knowledge' && <CharacterBinding characters={characters} value={entry.character_id} onChange={(id, name) => setEntry({ ...entry, character_id: id || undefined, subject: name ?? entry.subject })} />}
    <label className="field"><span>{entry.kind === 'knowledge' ? 'Character or viewpoint name' : 'Decision title'}</span><input maxLength={160} value={entry.subject} onChange={event => setEntry({ ...entry, subject: event.target.value })} /></label>
    <label className="field" htmlFor={inputId + '-state'}><span id={inputId + '-state-label'}>Decision state</span><select aria-labelledby={inputId + '-state-label'} id={inputId + '-state'} value={entry.stance} onChange={event => setEntry({ ...entry, stance: event.target.value })}>{states[entry.kind].map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
    <label className="field"><span>Your interpretation or instruction</span><textarea rows={4} maxLength={1200} value={entry.text} onChange={event => setEntry({ ...entry, text: event.target.value })} /></label>
    <p className="subtle">{entry.kind === 'knowledge' ? 'Name the character explicitly. A belief can be wrong; unknown knowledge stays unknown. These are narration instructions, not an automatic detector of who witnessed each event.' : 'Keep the distinction between evidence, your interpretation, and accepted story events.'} Select {entry.kind === 'conflict' ? 'two to eight' : 'one to eight'} supporting excerpts.</p>
    <ControlSources branch={branch} library={entry.kind === 'knowledge'} selected={entry.sources} onToggle={toggle} />
    <div className="import-downloads"><button className="button primary" disabled={!valid} onClick={() => onKeep(entry)}>Keep in draft</button><button className="button" onClick={onCancel}>Cancel editing</button></div>
  </div>
}

export function ControlHistory({ branchId, onLoad }: { branchId: string; onLoad: (entries: Entry[]) => void }) {
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(0)
  const action = useAction()
  const query = useQuery({ queryKey: ['memory-control-history', branchId, page], queryFn: () => api<{ id: string; created_at: string }[]>('/branches/' + branchId + '/memory-control-history?offset=' + page * 25), enabled: open })
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const load = (id: string) => action.run(async () => { const result = await api<{ payload: { entries: Entry[] } }>('/branches/' + branchId + '/memory-control-history/' + id); if (alive.current) onLoad(result.payload.entries) })
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Earlier author decisions</summary><div className="form-stack authoring-history"><p className="subtle">Load a version into the draft, review its evidence, then save a new version. Earlier decisions remain preserved.</p><ErrorNotice message={query.error?.message || action.error} />
    {query.data?.map(version => <button className="button" key={version.id} disabled={action.busy} onClick={() => load(version.id)}>Load version from {new Date(version.created_at).toLocaleString()}</button>)}
    <div className="import-downloads"><button className="button" disabled={!page || query.isFetching} onClick={() => setPage(page - 1)}>Newer decisions</button><button className="button" disabled={query.data?.length !== 25 || query.isFetching} onClick={() => setPage(page + 1)}>Older decisions</button></div>
  </div></details>
}

export function UnavailableDecisions({ entries = [], onEdit }: { entries?: Entry[]; onEdit: (entry: Entry) => void }) {
  if (!entries.length) return null
  return <div className="prepared-card form-stack"><h4>Evidence needs review ({entries.length})</h4><p>These decisions use a Character or source edition no longer available on this path. Their grants are excluded from new requests; does-not-know decisions still block any matching evidence. Saving without re-adding them retires these decisions, including their restrictions. The originals remain in Earlier author decisions.</p>
    {entries.map(entry => <div key={entry.id}><strong>{entry.subject}</strong><p>{entry.text}</p><button className="button" onClick={() => onEdit(entry)}>Review for this path</button></div>)}
    <small>To grant a new edition, remove the old excerpts and explicitly select their replacements.</small>
  </div>
}
