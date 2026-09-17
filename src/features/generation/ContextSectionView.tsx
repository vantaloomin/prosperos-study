import { useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { ContextPage, ContextRequest, ContextSection } from './contextTypes'

interface Props { branchId: string; request: ContextRequest; fingerprint: string; section: ContextSection }

export function ContextSectionView(props: Props) {
  const [open, setOpen] = useState(false)
  const { section } = props
  return <details className="context-section" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary><span><strong>{section.label}</strong><small>{section.description}</small></span><span>≈ {section.estimated_tokens.toLocaleString()}<small>{section.bytes.toLocaleString()} bytes</small></span></summary>
    {open && <SectionPage {...props} />}
  </details>
}

function SectionPage({ branchId, request, fingerprint, section }: Props) {
  const [offset, setOffset] = useState(0)
  const [view, setView] = useState('readable')
  const query = useQuery({ queryKey: ['context-section', branchId, request, fingerprint, section.key, offset, view],
    queryFn: () => api<ContextPage>(`/branches/${branchId}/context-preview/section`, { ...request, fingerprint, section: section.key, offset, view }),
    retry: false, refetchOnWindowFocus: false, gcTime: 0, placeholderData: keepPreviousData })
  return <div className="context-section-body"><label className="context-view-choice">View<select aria-label={`${section.label} view`} value={view} onChange={(event) => { setOffset(0); setView(event.target.value) }}><option value="readable">Readable sources</option><option value="exact">Exact request text</option></select></label><ErrorNotice message={query.error?.message} />
    {query.isPending && <Loading label="Reading this input section…" />}
    {query.data && <><SourceLabels page={query.data} />
      <p className="subtle">{view === 'exact' ? 'Exact application text, including JSON field names and record metadata. Section estimates include these bytes.' : 'Prose and source references for reading. Choose Exact request text to inspect the serialized data counted in the budget.'}</p>
      <InputPage page={query.data} busy={query.isPlaceholderData} label={`${section.label} ${view} input`} readable={view === 'readable'} />
      <PageControls page={query.data} busy={query.isFetching} onPage={setOffset} /></>}
  </div>
}

function InputPage({ page, busy, label, readable }: { page: ContextPage; busy: boolean; label: string; readable: boolean }) {
  return <pre className={readable ? 'context-readable' : ''} tabIndex={0} aria-label={label} aria-busy={busy}>{busy ? 'Reading this page…' : page.text || '(Empty)'}</pre>
}

function PageControls({ page, busy, onPage }: { page: ContextPage; busy: boolean; onPage: (offset: number) => void }) {
  return <div className="context-page-controls"><button className="button quiet" disabled={page.offset === 0} aria-disabled={busy} onClick={() => { if (!busy) onPage(Math.max(0, page.offset - 8000)) }}>Previous text</button>
    <span className="subtle" role="status">{page.total_characters ? page.offset + 1 : 0}–{Math.min(page.offset + 8000, page.total_characters)} of {page.total_characters.toLocaleString()} characters</span>
    <button className="button quiet" disabled={page.next_offset === null} aria-disabled={busy} onClick={() => { if (!busy && page.next_offset !== null) onPage(page.next_offset) }}>Next text</button></div>
}

function SourceLabels({ page }: { page: ContextPage }) {
  if (!page.source_count) return null
  return <details className="context-source-labels"><summary>Source references ({page.source_count.toLocaleString()})</summary>
    <ul>{page.sources.map((source) => <li key={source}>{source}</li>)}</ul>
    {page.source_count > page.sources.length && <p className="subtle">The first {page.sources.length} references are listed here. All references remain in the paged exact input below.</p>}</details>
}
