import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { DeckEditor } from './DeckEditor'
import { deckDraft, type DeckDraft } from './draft'
import { DeckPlay } from './DeckPlay'
import { DeckPackExport, DeckPackImport } from './DeckPacks'
import type { Deck, PackDocument } from './types'
import '../writing/writing.css'

type Editor = { initial: DeckDraft; version?: Deck; key: string } | null
type Pack = { mode: 'import'; starter?: PackDocument } | { mode: 'export'; decks: Deck[]; selected: string[] } | null

export function InspirationLibrary() {
  const [archived, setArchived] = useState(false), [search, setSearch] = useState('')
  const query = useQuery({ queryKey: ['inspiration', 'decks', archived], queryFn: () => api<Deck[]>(`/inspiration/decks?include_archived=${archived}`) })
  const starters = useQuery({ queryKey: ['inspiration', 'starters'], queryFn: () => api<{ key: string; document: PackDocument }[]>('/inspiration/starters') })
  const [editor, setEditor] = useState<Editor>(null), [play, setPlay] = useState<Deck | null>(null), [pack, setPack] = useState<Pack>(null)
  const decks = query.data ?? [], visible = decks.filter(item => item.name.toLowerCase().includes(search.toLowerCase()))
  const edit = (deck: Deck) => setEditor({ initial: deckDraft(deck), version: deck, key: `roleplay:deck-editor:${deck.id}` })
  const copy = (deck: Deck) => setEditor({ initial: { ...deckDraft(deck), name: `${deck.name.slice(0, 150)} copy` }, key: `roleplay:deck-copy:${deck.id}` })
  const exportVersion = (deck: Deck) => setPack({ mode: 'export', decks: [deck], selected: [deck.id] })
  return <section className="form-stack"><header className="deck-actions"><div><h2>Inspiration decks</h2><p>Weighted ideas, recorded only when you choose to draw.</p></div><button className="button primary" onClick={() => setEditor({ initial: deckDraft(), key: 'roleplay:deck-editor:new' })}>Create deck</button><button className="button" onClick={() => setPack({ mode: 'import' })}>Import collection</button><button className="button" disabled={!decks.length} onClick={() => setPack({ mode: 'export', decks, selected: [] })}>Export collection</button></header>
    <div className="deck-actions"><input aria-label="Search inspiration decks" placeholder="Search decks" value={search} onChange={event => setSearch(event.target.value)} /><label className="check-row"><input type="checkbox" checked={archived} onChange={event => setArchived(event.target.checked)} />Include archived decks</label></div><ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}{!query.isPending && !visible.length && <p>No matching decks. Create one or review a starter below.</p>}
    <div className="writing-resource-grid">{visible.map(deck => <DeckCard key={deck.deck_id} deck={deck} onEdit={edit} onCopy={copy} onPlay={setPlay} onExport={exportVersion} />)}</div>
    <section className="form-stack"><h3>Editable starter collections</h3><ErrorNotice message={starters.error?.message} /><div className="writing-resource-grid">{starters.data?.map(item => <article className="writing-resource-card form-stack" key={item.key}><h4>{String(item.document.name)}</h4><p>{String(item.document.description)}</p><button className="button" onClick={() => setPack({ mode: 'import', starter: item.document })}>Review {String(item.document.name)}</button></article>)}</div></section>
    {editor && <DeckEditor key={editor.key} initial={editor.initial} version={editor.version} draftKey={editor.key} onClose={() => setEditor(null)} />}{play && <DeckPlay deck={play} onClose={() => setPlay(null)} />}<PackModal pack={pack} decks={decks} onClose={() => setPack(null)} />
  </section>
}

function PackModal({ pack, decks, onClose }: { pack: Pack; decks: Deck[]; onClose: () => void }) {
  if (!pack) return null
  return pack.mode === 'import' ? <DeckPackImport decks={decks} starter={pack.starter} onClose={onClose} /> : <DeckPackExport decks={pack.decks} initial={pack.selected} onClose={onClose} />
}

function DeckCard({ deck, onEdit, onCopy, onPlay, onExport }: { deck: Deck; onEdit: (deck: Deck) => void; onCopy: (deck: Deck) => void; onPlay: (deck: Deck) => void; onExport: (deck: Deck) => void }) {
  const action = useAction({ queryKey: ['inspiration'] })
  const toggle = () => action.run(async () => { await api(`/inspiration/decks/${deck.deck_id}/archived`, { operation_id: operationId(), expected_revision: deck.revision, archived: !deck.archived }, 'PUT') })
  return <article className="writing-resource-card form-stack"><h3>{deck.name} · v{deck.number}</h3><p>{deck.description}</p><p>{deck.content.cards.length} cards · with replacement{deck.archived ? ' · Archived' : ''}</p><div className="deck-actions"><button className="button" onClick={() => onPlay(deck)}>Preview & draw</button><button className="text-button" onClick={() => onEdit(deck)}>Edit deck</button><button className="text-button" onClick={() => onCopy(deck)}>Duplicate deck</button><button className="text-button" onClick={() => onExport(deck)}>Export version</button><button className="text-button" disabled={action.busy} onClick={toggle}>{deck.archived ? 'Restore deck' : 'Archive deck'}</button></div><ErrorNotice message={action.error} /><DeckHistory deck={deck} onPlay={onPlay} onExport={onExport} /></article>
}

function DeckHistory({ deck, onPlay, onExport }: { deck: Deck; onPlay: (deck: Deck) => void; onExport: (deck: Deck) => void }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['inspiration', 'versions', deck.deck_id, deck.id], queryFn: () => api<Deck[]>(`/inspiration/decks/${deck.deck_id}/versions`), enabled: open })
  return <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Version history & original packs</summary><ErrorNotice message={query.error?.message} />{open && query.data?.map(item => <section key={item.id} className="form-stack deck-pack-card"><strong>{item.name} · v{item.number}</strong><p>{item.note}</p><div className="deck-actions"><button className="text-button" onClick={() => onPlay(item)}>Inspect & draw v{item.number}</button><button className="text-button" onClick={() => onExport(item)}>Export v{item.number}</button></div><PackOrigins versionId={item.id} /></section>)}</details>
}

function PackOrigins({ versionId }: { versionId: string }) {
  const query = useQuery({ queryKey: ['inspiration', 'origins', versionId], queryFn: () => api<{ id: string; filename: string; item_key: string }[]>(`/inspiration/versions/${versionId}/imports`) })
  return <><ErrorNotice message={query.error?.message} />{query.data?.map(source => <a className="text-button" key={source.id} href={`/api/inspiration/packs/${source.id}/original`} download>Original collection: {source.filename} · {source.item_key}</a>)}</>
}
