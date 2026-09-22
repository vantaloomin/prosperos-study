import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { Field, TextField } from '../../components/Fields'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import { readImportFile } from '../library/importTypes'
import { DeckMetadata } from './DeckEditor'
import type { Deck, PackChoice, PackDocument, PackReport } from './types'
import { usePackPublication } from './usePackPublication'

export function DeckPackImport({ decks, starter, onClose }: { decks: Deck[]; starter?: PackDocument; onClose: () => void }) {
  const [id, setId] = usePersistent<string | null>(starter ? `roleplay:inspiration-starter-review:${String(starter.name)}` : 'roleplay:inspiration-pack-review', null)
  const query = useQuery({ queryKey: ['inspiration', 'pack', id], queryFn: () => api<PackReport>(`/inspiration/packs/${id}`), enabled: !!id })
  const action = useAction({ queryKey: ['inspiration'] })
  const stage = (file: File) => action.run(async () => {
    if (file.size > 8 * 1024 * 1024) throw new Error('Choose an inspiration pack no larger than 8 MiB.')
    const result = await api<PackReport>('/inspiration/packs', { filename: file.name, source_base64: await readImportFile(file) })
    setId(result.id)
  })
  return <Modal open wide title="Import inspiration collection" description="Review the decks, weights, duplicate decisions and unsupported metadata before publication." onClose={onClose}><div className="dialog-body form-stack">{starter && <button className="button" disabled={action.busy} onClick={() => stage(new File([JSON.stringify(starter)], 'starter.inspiration.json', { type: 'application/json' }))}>Load {String(starter.name)} for review</button>}
    <label className="field"><span>Choose inspiration pack</span><input aria-label="Choose inspiration pack" type="file" accept=".json" disabled={action.busy} onChange={event => { const file = event.target.files?.[0]; event.target.value = ''; if (file) void stage(file) }} /></label><p className="subtle">Format 1 · up to 32 decks, 500 cards each and 8 MiB total. Published sources travel with their imported deck versions in private archives.</p><ErrorNotice message={action.error || query.error?.message} />{action.busy && <Loading label="Inspecting the collection…" />}{query.data && !action.busy && <PackReview key={query.data.id} report={query.data} decks={decks} />}</div><footer className="dialog-footer"><button className="button" onClick={onClose}>Done</button></footer></Modal>
}

function PackReview({ report, decks }: { report: PackReport; decks: Deck[] }) {
  const key = `roleplay:inspiration-pack-choices:${report.id}`
  const [choices, setChoices] = usePersistent<PackChoice[]>(key, report.decks.map(item => ({ key: item.key, included: true, duplicate_action: 'skip', target_deck_id: null, expected_version_id: null })), true)
  const [reviewed, setReviewed] = useState(false)
  const publication = usePackPublication(report)
  const { action, result, pending } = publication
  const patch = (id: string, change: Partial<PackChoice>) => { setChoices(choices.map(item => item.key === id ? { ...item, ...change } : item)); setReviewed(false) }
  return <section className="form-stack"><h3>{report.name}</h3><p>{report.description}</p><p>{report.compatibility}</p><p>{report.activation}</p><a className="text-button" href={`/api/inspiration/packs/${report.id}/original`} download>Download exact original collection</a>
    {result ? <div className="import-compatibility"><h3>Collection result saved</h3>{result.versions.map(item => <p key={item.id}>{item.name} · v{item.number} published</p>)}{result.skipped.map(item => <p key={item.key}>{item.key} · duplicate left unchanged</p>)}<p>Publishing did not draw a card or change a Story.</p><button className="button" onClick={() => { publication.reset(); setReviewed(false) }}>Review another import</button></div> : <><fieldset className="deck-controls form-stack" disabled={action.busy || pending}>{report.decks.map((item, index) => <PackDeckReview key={item.key} item={item} choice={choices[index]} decks={decks} onChange={change => patch(item.key, change)} />)}</fieldset><label className="check-row"><input type="checkbox" checked={reviewed} disabled={pending} onChange={event => setReviewed(event.target.checked)} />I reviewed the selected decks, weights, duplicate choices and compatibility.</label><PackPublishButton pending={pending} busy={action.busy} reviewed={reviewed && choices.some(item => item.included)} retry={publication.retry} publish={() => publication.publish(choices, reviewed)} /></>}<ErrorNotice message={publication.error} /></section>
}

function PackPublishButton({ pending, busy, reviewed, retry, publish }: { pending: boolean; busy: boolean; reviewed: boolean; retry: () => void; publish: () => void }) {
  if (pending) return <div className="import-compatibility"><p>A saved import request is pending. Retry its frozen choices to recover the same result.</p><button className="button" disabled={busy} onClick={retry}>Retry saved collection import</button></div>
  return <button className="button primary" disabled={!reviewed || busy} onClick={publish}>Import reviewed decks</button>
}

function PackDeckReview({ item, choice, decks, onChange }: { item: PackReport['decks'][number]; choice: PackChoice; decks: Deck[]; onChange: (patch: Partial<PackChoice>) => void }) {
  const target = (id: string) => { const deck = decks.find(value => value.deck_id === id); onChange({ target_deck_id: deck?.deck_id ?? null, expected_version_id: deck?.id ?? null }) }
  return <article className="deck-card-editor form-stack"><label className="check-row"><input type="checkbox" checked={choice.included} onChange={event => onChange({ included: event.target.checked })} />Include {item.name}</label><p>{item.description}</p><p>{item.content.cards.length} cards · weighted draws with replacement</p><details><summary>Inspect all cards and weights</summary>{item.content.cards.map(card => <div className="form-stack deck-pack-card" key={card.id}><h4>{card.title} · weight {card.weight}{!card.enabled && ' · disabled'}</h4><p className="deck-card-text">{card.text}</p><small>{card.tags.join(', ')}</small></div>)}</details><DeckMetadata value={item.unsupported} />
    {item.duplicates.length > 0 && <p>Matching card definitions: {item.duplicates.map(match => `${match.name} v${match.number}`).join(', ')}. Names and unsupported metadata may differ.</p>}
    <label className="field"><span>{item.name} duplicate decision</span><select aria-label={`${item.name} duplicate decision`} value={choice.duplicate_action} onChange={event => onChange({ duplicate_action: event.target.value as 'skip' | 'new' })}><option value="skip">Skip matching card definitions</option><option value="new">Deliberately create another deck</option></select></label>
    <label className="field"><span>{item.name} destination</span><select aria-label={`${item.name} destination`} value={choice.target_deck_id ?? ''} onChange={event => target(event.target.value)}><option value="">Create a separate deck</option>{decks.map(deck => <option key={deck.deck_id} value={deck.deck_id}>Update {deck.name} · currently v{deck.number}</option>)}</select><small>Updates require this exact identity and reviewed current version. Earlier versions and draw results remain unchanged.</small></label></article>
}

export function DeckPackExport({ decks, initial, onClose }: { decks: Deck[]; initial: string[]; onClose: () => void }) {
  const [selected, setSelected] = useState(initial), [name, setName] = useState('My inspiration collection'), [description, setDescription] = useState('')
  const [prepared, setPrepared] = useState<{ input: string; document: PackDocument } | null>(null)
  const action = useAction({ queryKey: ['inspiration', 'export'] })
  const body = { name, description, version_ids: selected }, input = JSON.stringify(body)
  const ready = prepared?.input === input ? prepared.document : null
  const prepare = () => action.run(async () => { setPrepared({ input, document: await api<PackDocument>('/inspiration/packs/export', body) }) })
  return <Modal open wide title="Export inspiration collection" description="Share selected deck versions as a portable, self-contained JSON pack." onClose={onClose}><div className="dialog-body form-stack"><Field label="Collection name" maxLength={160} value={name} onChange={event => setName(event.target.value)} /><TextField label="Collection description" maxLength={3000} rows={2} value={description} onChange={event => setDescription(event.target.value)} />{decks.map(deck => <label className="check-row" key={deck.id}><input type="checkbox" checked={selected.includes(deck.id)} onChange={() => setSelected(selected.includes(deck.id) ? selected.filter(id => id !== deck.id) : [...selected, deck.id])} />{deck.name} · v{deck.number}</label>)}<p>Up to 32 selected versions and 8 MiB. Draw history, Stories, conversations and model configuration are excluded. Known private connection metadata is omitted.</p><ErrorNotice message={action.error} /><button className="button" disabled={!selected.length || !name.trim() || action.busy} onClick={prepare}>Prepare collection</button>{ready && <details open><summary>Inspect export contents</summary><pre className="deck-json">{JSON.stringify(ready, null, 2)}</pre></details>}</div><footer className="dialog-footer"><button className="text-button" onClick={onClose}>Close</button><button className="button primary" disabled={!ready} onClick={() => { if (ready) downloadPack(ready, name) }}>Download inspiration collection</button></footer></Modal>
}

function downloadPack(document: PackDocument, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(document, null, 2) + '\n'], { type: 'application/json' }))
  const link = window.document.createElement('a')
  link.href = url; link.download = (name.replace(/[^a-z0-9_-]+/gi, '-').slice(0, 80) || 'inspiration') + '.inspiration.json'; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
