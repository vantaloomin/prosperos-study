import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../../api'
import { Field } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { useAction } from '../../hooks/useAction'
import type { LoreEntry } from './loreTypes'

interface Candidate { id: string; title: string; path: string; import_id: string; filename: string }
interface Proposal { entry: LoreEntry; original_fields: Record<string, unknown>; notice: string }

export function ImportedEntryPicker({ versionId, entries, onAdd, onClose }: { versionId: string; entries: LoreEntry[]; onAdd: (entry: LoreEntry) => void; onClose: () => void }) {
  const query = useQuery({ queryKey: ['imported-entries', versionId], queryFn: () => api<Candidate[]>(`/versions/${versionId}/imported-entries`) })
  const [filter, setFilter] = useState('')
  const [proposal, setProposal] = useState<Proposal | null>(null)
  const action = useAction()
  const inspect = (item: Candidate) => action.run(async () => setProposal(await api<Proposal>(`/versions/${versionId}/imported-entry?import_id=${encodeURIComponent(item.import_id)}&path=${encodeURIComponent(item.path)}`)))
  const alreadyAdded = entries.some((entry) => entry.id === proposal?.entry.id)
  return <Modal open wide title="Bring in preserved entries" description="Choose an entry from this book’s original import. It becomes an editable draft entry with its toggle off." onClose={onClose}>
    <div className="dialog-body form-stack"><Field label="Find preserved entry" value={filter} onChange={(e) => setFilter(e.target.value)} autoFocus />
      <ErrorNotice message={action.error || query.error?.message} />{query.isPending && <p role="status">Loading preserved entries…</p>}
      {query.isError && <button className="button" onClick={() => void query.refetch()}>Retry loading entries</button>}
      <Candidates items={query.data} filter={filter} busy={action.busy} onInspect={inspect} />
      <ProposalDetails proposal={proposal} />
    </div><footer className="dialog-footer"><button className="text-button" onClick={onClose}>Cancel</button><button className="button primary" disabled={!proposal || alreadyAdded || entries.length >= 500} onClick={() => { if (proposal) { onAdd(proposal.entry); onClose() } }}>{alreadyAdded ? 'Already in draft' : 'Add to draft (off)'}</button></footer>
  </Modal>
}

function Candidates({ items, filter, busy, onInspect }: { items?: Candidate[]; filter: string; busy: boolean; onInspect: (item: Candidate) => void }) {
  if (!items) return null
  const candidates = items.filter((item) => `${item.title} ${item.path}`.toLocaleLowerCase().includes(filter.toLocaleLowerCase()))
  return <>{candidates.length === 0 && <p>No matching entries in this version’s preserved imports.</p>}
    <div className="lore-entry-buttons">{candidates.slice(0, 80).map((item) => <button className="lore-entry-select" key={`${item.import_id}:${item.path}`} onClick={() => onInspect(item)} aria-disabled={busy}><span>{item.title}</span><small>{item.path}</small></button>)}</div>
    {candidates.length > 80 && <p className="subtle">Showing 80 matches. Refine the search for more.</p>}</>
}

function ProposalDetails({ proposal }: { proposal: Proposal | null }) {
  if (!proposal) return null
  return <section className="form-stack"><h3>{proposal.entry.title}</h3><p className="subtle">{proposal.notice}</p><pre className="lore-prose-preview">{proposal.entry.text.slice(0, 20000)}</pre><p className="subtle">Prose preview limited to 20,000 characters; the complete entry is copied.</p><details className="advanced-settings"><summary>Original activation fields</summary><pre className="lore-prose-preview">{JSON.stringify(proposal.original_fields, null, 2)}</pre></details><p className="subtle">Proposed primary keywords: {proposal.entry.keywords.join(', ') || 'none'} · activation: {proposal.entry.activation} · toggle: off</p></section>
}
