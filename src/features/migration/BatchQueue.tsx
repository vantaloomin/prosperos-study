import { useState } from 'react'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Selection } from '../../types'
import { BatchItemReview } from './BatchItemReview'
import { BatchResult } from './BatchResult'
import { batchKindLabels, batchStatusLabels, type BatchItem, type BatchKind, type MigrationBatch } from './batchTypes'

export function BatchQueue({ batch, onOpen }: { batch: MigrationBatch; onOpen: (selection: Selection) => void }) {
  const [selected, setSelected] = usePersistent(`roleplay:batch-selection:${batch.id}`, batch.items[0].id)
  const [publishing, setPublishing] = useState(false)
  const item = batch.items.find(row => row.id === selected) ?? batch.items[0]
  // A changed queue can retire its mounted review. Do not refetch that old
  // review concurrently with the queue; it refreshes when opened again.
  const action = useAction({ predicate: query => !['batch-item-preview', 'batch-bundle-preview'].includes(String(query.queryKey[0])) })
  const finished = batch.items.filter(row => ['complete', 'omitted', 'rejected'].includes(row.status)).length
  const update = (request: () => Promise<unknown>) => action.run(async () => { await request() })
  const choose = (kind: BatchKind) => update(() => api(`/migration/batch-items/${item.id}/interpretation`, { expected_revision: item.revision, kind }))
  const skip = () => update(() => api(`/migration/batch-items/${item.id}/selection`, { expected_revision: item.revision, skipped: item.status !== 'omitted' }, 'PUT'))
  const retry = () => update(() => api(`/migration/batch-items/${item.id}/retry`, { expected_revision: item.revision }))
  return <section className="form-stack"><h3>Migration review queue</h3><p>{finished} of {batch.items.length} files resolved. Review and publish each included file deliberately; importing starts no model work.</p><p className="subtle">This queue and its saved results stay on this installation across restart. Published foreign sources travel with their imported Story or Library versions in private archives. Original native files remain downloadable here; private archives do not nest old archive files or unfinished queues.</p>
    <div className="migration-batch-list" role="group" aria-label="Migration files">{batch.items.map(row => <button className="button migration-batch-row" key={row.id} aria-pressed={item.id === row.id} disabled={publishing || action.busy} onClick={() => setSelected(row.id)}><strong>{row.position + 1}. {row.filename}</strong><span>{batchStatusLabels[row.status]}{row.kind && ` · ${batchKindLabels[row.kind]}`}</span><small>{row.batch_duplicates.length ? 'Matching source proposals in this batch' : ''}</small></button>)}</div>
    <section className="form-stack migration-batch-detail" aria-label={`Review ${item.filename}`}><h3>{item.filename}</h3><BatchSourceLinks item={item} /><BatchMatches item={item} /><ErrorNotice message={item.error || action.error} />
      <BatchControls item={item} busy={action.busy || publishing} choose={choose} skip={skip} retry={retry} />
      {item.status === 'review' && <BatchItemReview key={`${item.id}:${item.import_id}`} item={item} onOpen={onOpen} onPublishing={setPublishing} />}
      {item.status === 'complete' && <BatchResult item={item} onOpen={onOpen} />}
      {item.status === 'rejected' && <p>This file was not converted or published, and its rejected bytes were not retained. Correct a copy of the file and select it for a new batch; other files can continue.</p>}
    </section>
  </section>
}

function BatchSourceLinks({ item }: { item: BatchItem }) {
  return <div className="import-downloads">{item.source_sha256 && <a className="text-button" href={`/api/migration/batch-items/${item.id}/original`} download>Download exact batch source</a>}<a className="text-button" href={`/api/migration/batch-items/${item.id}/report`} download>Download item report & result</a></div>
}

function BatchMatches({ item }: { item: BatchItem }) {
  const matches = [...item.batch_duplicates, ...item.prior_duplicates]
  if (!matches.length) return null
  return <section className="import-compatibility"><h4>Matching source material</h4>{matches.map((match, index) => <p key={`${match.item_id}:${match.kind}:${index}`}>{match.filename} · {batchKindLabels[match.kind]} · {match.match === 'exact-source' ? 'exact file bytes' : 'equivalent proposed content'} · {match.parts.join(', ')}</p>)}<p className="subtle">Another queued source may not have been published yet. Publication rechecks earlier successful imports and skips matches by default. A deliberate new-copy decision is available in the review below.</p></section>
}

function BatchControls({ item, busy, choose, skip, retry }: { item: BatchItem; busy: boolean; choose: (kind: BatchKind) => void; skip: () => void; retry: () => void }) {
  if (item.status === 'publishing') return <div className="import-compatibility"><p>Publication was started with frozen choices. Retry to recover the same recorded result; changing those choices cannot create a second import.</p><button className="button primary" disabled={busy} onClick={retry}>Retry saved publication</button></div>
  if (item.status === 'complete' || item.status === 'rejected') return null
  return <div className="form-stack"><InterpretationChoices item={item} busy={busy} choose={choose} />{['review', 'choose', 'omitted'].includes(item.status) && <button className="button" disabled={busy} onClick={skip}>{item.status === 'omitted' ? 'Include this file again' : 'Omit this file'}</button>}</div>
}

function InterpretationChoices({ item, busy, choose }: { item: BatchItem; busy: boolean; choose: (kind: BatchKind) => void }) {
  if (item.status === 'omitted') return null
  const options = Object.entries(item.candidates) as [BatchKind, { filename: string; label: string }][]
  if (options.length === 1 && item.status === 'review') return null
  return <div className="import-compatibility"><h4>Choose how to interpret this source</h4><p>Text can be Story messages or world knowledge. Select its meaning before reviewing mappings; choosing a reader publishes nothing.</p>{options.map(([kind, candidate]) => <button className="button" key={kind} disabled={busy} onClick={() => choose(kind)}>Review as {batchKindLabels[kind]} · {candidate.label}</button>)}</div>
}
