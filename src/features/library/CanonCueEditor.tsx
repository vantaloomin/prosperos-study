import { useLayoutEffect, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { TextField } from '../../components/Fields'
import type { AssetContent } from '../../types'
import type { CueFields, CueReport, CueRow } from './canonCueTypes'

interface Props { row: CueRow; content: AssetContent; versionId?: string; busy: boolean; onKeep: (fields: CueFields) => void; onCancel: () => void }

export function CanonCueEditor({ row, content, versionId, busy, onKeep, onCancel }: Props) {
  const [summary, setSummary] = useState(row.cue.summary)
  const [topics, setTopics] = useState(row.cue.topics.join('\n'))
  const [aliases, setAliases] = useState(row.cue.aliases.join('\n'))
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  const fields = () => ({ summary, topics: editedTerms(topics, row.cue.topics), aliases: editedTerms(aliases, row.cue.aliases) })
  return <form className="form-stack" onSubmit={event => { event.preventDefault(); onKeep(fields()) }}>
    <h3 ref={heading} tabIndex={-1}>Edit search aid {row.number}</h3>
    {row.status === 'stale' && <p className="canon-cue-state">Inactive · its source has changed. Editing these fields will keep the original source link; it will remain inactive until that exact source is restored.</p>}
    <CueSourceView row={row} content={content} versionId={versionId} />
    <fieldset disabled={busy} className="form-stack canon-cue-fields">
      <TextField label="Retrieval summary" rows={5} maxLength={32000} value={summary} onChange={event => setSummary(event.target.value)} hint="A search aid for this excerpt, not new Canon. Preserve uncertainty and qualifications." />
      <TextField label="Topics · one per line" rows={3} maxLength={512255} value={topics} onChange={event => setTopics(event.target.value)} />
      <TextField label="Aliases & alternate phrases · one per line" rows={3} maxLength={512255} value={aliases} onChange={event => setAliases(event.target.value)} hint="Empty lines are ignored. Existing imported phrases are preserved until you edit them." />
      <div className="import-downloads"><button className="button primary" type="submit">{busy ? 'Keeping changes…' : 'Keep aid in Canon draft'}</button><button className="button" type="button" onClick={onCancel}>Cancel editing</button></div>
    </fieldset>
  </form>
}

function editedTerms(value: string, original: string[]) {
  return value === original.join('\n') ? original : value.split('\n').map(term => term.trim()).filter(Boolean)
}

function CueSourceView({ row, content, versionId }: Pick<Props, 'row' | 'content' | 'versionId'>) {
  const [offset, setOffset] = useState(0)
  const query = useQuery({ queryKey: ['canon-cue-source', content, versionId, row.id, offset], staleTime: Infinity, placeholderData: keepPreviousData,
    initialData: offset === 0 ? { items: [row] } : undefined,
    queryFn: () => api<Pick<CueReport, 'items'>>('/canon/cues-preview', { content, source_version_id: versionId, cue_id: row.id, source_offset: offset }) })
  const source = query.data?.items[0].source
  return <details open className="canon-cue-evidence"><summary>Source for this aid</summary>
    <ErrorNotice message={query.error?.message} />
    {source ? <><p className="subtle">{source.origin === 'draft' ? 'Exact source in this draft' : `Preserved source from published v${source.version}`} · characters {source.offset + 1}–{source.end} of {source.length}</p>
      <pre className="import-document" tabIndex={0}>{source.text}</pre>
      {source.length > 2400 && <nav className="import-downloads" aria-label="Search-aid source pages"><button className="button" type="button" disabled={!source.offset || query.isFetching} onClick={() => setOffset(Math.max(0, source.offset - 2400))}>Earlier source text</button><button className="button" type="button" disabled={source.next_offset === null || query.isFetching} onClick={() => setOffset(source.next_offset!)}>More source text</button></nav>}
    </> : <p className="subtle">{query.isPending ? 'Reading the source…' : 'The original excerpt is not available in this draft or its published version. Review an earlier Canon version for the original text; this aid stays inactive.'}</p>}
  </details>
}
