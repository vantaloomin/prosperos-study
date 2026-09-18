import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useQuery, type UseQueryResult } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { AssetContent, AssetVersion } from '../../types'
import { CanonCueEditor } from './CanonCueEditor'
import type { CanonPolicy, CueFields, CueFilter, CueReport, CueRow } from './canonCueTypes'

interface Props { content: AssetContent; asset?: AssetVersion; onChange: (patch: Partial<AssetContent>) => void; onClose: () => void }
interface Selection { row: CueRow; fingerprint: string }
interface Undo { before: CanonPolicy | undefined; after: string }

export function CanonCueManager(props: Props) {
  const [filter, setFilter] = useState<CueFilter>({ query: '', status: 'all', offset: 0 })
  const [editing, setEditing] = useState<Selection | null>(null)
  const [notice, setNotice] = useState('')
  const [undo, setUndo] = useState<Undo | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const returnId = useRef('')
  const current = useRef(props)
  const alive = useRef(true)
  const action = useAction()
  useLayoutEffect(() => { current.current = props }, [props])
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const query = useQuery({ queryKey: ['canon-cues', props.content, props.asset?.id, filter],
    queryFn: () => api<CueReport>('/canon/cues-preview', { content: props.content, source_version_id: props.asset?.id, ...filter }) })
  useLayoutEffect(() => {
    if (!editing && returnId.current) { (document.getElementById('cue-edit-' + returnId.current) ?? heading.current)?.focus(); returnId.current = '' }
  }, [editing])
  const change = (selection: Selection, verb: 'edit' | 'remove', fields?: CueFields) => action.run(async () => {
    const before = current.current.content
    const patch = await api<Partial<AssetContent>>('/canon/cues-change', { content: before, expected_fingerprint: selection.fingerprint, cue_id: selection.row.id, action: verb, fields })
    if (!alive.current) return
    if (JSON.stringify(before) !== JSON.stringify(current.current.content)) throw new Error('This Canon draft changed while applying. Your later edits are preserved; reopen the aid and try again.')
    setUndo({ before: before.canon_recall, after: JSON.stringify({ ...before, ...patch }) })
    current.current.onChange(patch); returnId.current = selection.row.id; setEditing(null)
    setNotice(verb === 'remove' ? 'Removed from your unpublished draft. The original prose and published versions are unchanged.' : 'Search aid updated in your unpublished draft. Save a new Canon version when ready.')
    if (verb === 'remove') heading.current?.focus()
  })
  const undoChange = () => action.run(async () => {
    if (!undo) return
    if (JSON.stringify(current.current.content) !== undo.after) throw new Error('This draft has changed since that edit. Undo would overwrite later work, so those edits have been preserved.')
    current.current.onChange({ canon_recall: undo.before }); setUndo(null); setNotice('Restored the previous search aid in your draft.'); heading.current?.focus()
  })
  const open = (row: CueRow) => { if (query.data) { action.clearError(); returnId.current = row.id; setEditing({ row, fingerprint: query.data.fingerprint }) } }
  return <Modal open wide title="Manage Canon search aids" description="Review the phrases that help earlier Canon return. Kept changes stay in this draft until you publish a new version; existing Stories keep their pinned editions." onClose={props.onClose}>
    <div className="dialog-body form-stack canon-cue-manager"><h3 ref={heading} tabIndex={-1} className="canon-cue-heading">{editing ? 'Review an aid' : 'Your saved search aids'}</h3>
      <p role="status" className="subtle">{notice || 'Editing here uses no model and changes no Story.'}</p>
      <ErrorNotice message={action.error} />
      {editing ? <CanonCueEditor row={editing.row} content={props.content} versionId={props.asset?.id} busy={action.busy} onKeep={fields => change(editing, 'edit', fields)} onCancel={() => setEditing(null)} /> : <CueBrowse filter={filter} query={query} busy={action.busy} canUndo={!!undo}
        onFilter={next => { setFilter(next); setNotice(''); action.clearError() }} onEdit={open}
        onRemove={row => change({ row, fingerprint: query.data!.fingerprint }, 'remove')}
        onPage={offset => setFilter({ ...filter, offset })} onUndo={undoChange} />}
    </div><footer className="dialog-footer"><button className="button" onClick={props.onClose}>Back to Canon draft</button></footer>
  </Modal>
}

interface BrowseProps {
  filter: CueFilter; query: UseQueryResult<CueReport, Error>; busy: boolean; canUndo: boolean
  onFilter: (value: CueFilter) => void; onEdit: (row: CueRow) => void; onRemove: (row: CueRow) => void
  onPage: (offset: number) => void; onUndo: () => void
}

function CueBrowse({ filter, query, busy, canUndo, onFilter, onEdit, onRemove, onPage, onUndo }: BrowseProps) {
  const working = busy || query.isFetching
  return <><CueSearch filter={filter} busy={working} onFilter={onFilter} />
    <ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Reading saved aids…" />}
    {query.data && <CueList report={query.data} busy={working} onEdit={onEdit} onRemove={onRemove} onPage={onPage} />}
    {canUndo && <button className="button" disabled={busy} onClick={onUndo}>Undo last aid change</button>}
  </>
}

function CueSearch({ filter, busy, onFilter }: { filter: CueFilter; busy: boolean; onFilter: (value: CueFilter) => void }) {
  const [query, setQuery] = useState(filter.query)
  return <form className="canon-cue-search" onSubmit={event => { event.preventDefault(); onFilter({ ...filter, query, offset: 0 }) }}>
    <label className="field"><span>Find a saved aid</span><input maxLength={2000} value={query} onChange={event => setQuery(event.target.value)} placeholder="A summary, topic, or alternate phrase…" /></label>
    <label className="field"><span>Source status</span><select value={filter.status} onChange={event => onFilter({ query, status: event.target.value as CueFilter['status'], offset: 0 })}><option value="all">All aids</option><option value="active">Active aids</option><option value="stale">Source changed · inactive</option></select></label>
    <button type="submit" className="button" disabled={busy}>Find aids</button>
  </form>
}

function CueList({ report, busy, onEdit, onRemove, onPage }: { report: CueReport; busy: boolean; onEdit: (row: CueRow) => void; onRemove: (row: CueRow) => void; onPage: (offset: number) => void }) {
  return <><p role="status">{report.active} active · {report.stale} with changed sources · {report.matches} matching aids</p>
    {!report.items.length && <p className="subtle">No saved aids match this view. The original Markdown remains searchable without aids.</p>}
    {report.items.map(row => <article className="prepared-card form-stack canon-cue-card" key={row.id} aria-label={`Search aid ${row.number}`}>
      <div className="section-heading"><h4>Search aid {row.number}</h4><span className="canon-cue-state">{row.status === 'active' ? 'Active' : 'Source changed · inactive'}</span></div>
      <p className="canon-cue-summary" tabIndex={0}>{row.cue.summary || 'No retrieval summary.'}</p>
      <small>{row.cue.topics.length} topics · {row.cue.aliases.length} alternate phrases</small>
      <div className="import-downloads"><button id={'cue-edit-' + row.id} className="button" disabled={busy} onClick={() => onEdit(row)}>Review &amp; edit</button><button className="text-button" disabled={busy} onClick={() => onRemove(row)}>Remove from draft</button></div>
    </article>)}
    {report.matches > 12 && <nav className="import-downloads" aria-label="Saved search-aid pages"><button className="button" disabled={busy || report.offset === 0} onClick={() => onPage(Math.max(0, report.offset - 12))}>Previous aids</button><button className="button" disabled={busy || report.next_offset === null} onClick={() => onPage(report.next_offset!)}>Next aids</button></nav>}
  </>
}
