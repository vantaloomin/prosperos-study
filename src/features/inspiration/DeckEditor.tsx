import { useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { Field, TextField } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import { DeckPreview } from './DeckPreview'
import { splitTags, type Deck } from './types'
import { blankCard, type DeckDraft, type EditableCard } from './draft'

export function DeckEditor({ initial, version, draftKey, onClose }: { initial: DeckDraft; version?: Deck; draftKey: string; onClose: () => void }) {
  const [draft, setDraft] = usePersistent<DeckDraft>(draftKey, initial, true)
  const [page, setPage] = useState(0), [previewOpen, setPreviewOpen] = useState(false)
  const operation = useRef({ payload: '', id: operationId() })
  const action = useAction({ queryKey: ['inspiration'] })
  const patch = (change: Partial<DeckDraft>) => setDraft({ ...draft, ...change })
  const content = { cards: draft.cards.map(card => ({ ...card, weight: Number(card.weight), tags: splitTags(card.tags) })) }
  const currentPage = Math.min(page, Math.max(0, Math.ceil(draft.cards.length / 10) - 1))
  const save = () => action.run(async () => {
    const body = { name: draft.name, description: draft.description, note: draft.note, unsupported: draft.unsupported, content, ...(version ? { expected_version_id: version.id } : {}) }
    const payload = JSON.stringify(body)
    if (operation.current.payload !== payload) operation.current = { payload, id: operationId() }
    await api(version ? `/inspiration/decks/${version.deck_id}/versions` : '/inspiration/decks', { ...body, operation_id: operation.current.id })
    localStorage.removeItem(draftKey); onClose()
  })
  return <Modal open wide title={version ? `Edit ${version.name}` : 'Create an inspiration deck'} description="Publishing saves an immutable version. Earlier draws keep their original cards and weights." onClose={onClose}><div className="dialog-body form-stack"><Field label="Deck name" maxLength={160} value={draft.name} onChange={event => patch({ name: event.target.value })} /><TextField label="Deck description" rows={2} maxLength={3000} value={draft.description} onChange={event => patch({ description: event.target.value })} />
    <p>Use positive weights from 0.000001 to 1,000,000, with up to six decimal places. A weight of 3 is three times as likely as 1 among eligible cards. Drawing does not remove a card.</p>
    {draft.cards.slice(currentPage * 10, currentPage * 10 + 10).map((card, offset) => <CardEditor key={card.id} card={card} index={currentPage * 10 + offset + 1} removable={draft.cards.length > 1} onChange={change => patch({ cards: draft.cards.map(item => item.id === card.id ? { ...item, ...change } : item) })} onRemove={() => patch({ cards: draft.cards.filter(item => item.id !== card.id) })} />)}
    <div className="deck-actions"><button className="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous cards</button><span>{currentPage * 10 + 1}–{Math.min(draft.cards.length, currentPage * 10 + 10)} of {draft.cards.length}</span><button className="button" disabled={(currentPage + 1) * 10 >= draft.cards.length} onClick={() => setPage(currentPage + 1)}>Next cards</button><button className="button" disabled={draft.cards.length >= 500} onClick={() => { patch({ cards: [...draft.cards, blankCard()] }); setPage(Math.floor(draft.cards.length / 10)) }}>Add card</button></div>
    <button className="text-button" aria-expanded={previewOpen} onClick={() => setPreviewOpen(!previewOpen)}>Preview draft weights</button>{previewOpen && <DeckPreview content={content} />}
    <DeckMetadata value={draft.unsupported} /><TextField label="Deck version note" rows={2} maxLength={2000} value={draft.note} onChange={event => patch({ note: event.target.value })} /><ErrorNotice message={action.error} /></div><footer className="dialog-footer"><button className="text-button" onClick={onClose}>Close · keep draft</button><button className="button primary" disabled={!draft.name.trim() || action.busy} onClick={save}>Publish deck version</button></footer></Modal>
}

function CardEditor({ card, index, removable, onChange, onRemove }: { card: EditableCard; index: number; removable: boolean; onChange: (value: Partial<EditableCard>) => void; onRemove: () => void }) {
  return <section className="deck-card-editor form-stack" aria-label={`Card ${index}`}><h3>Card {index}</h3><Field label={`Card ${index} title`} value={card.title} maxLength={160} onChange={event => onChange({ title: event.target.value })} /><TextField label={`Card ${index} text`} rows={3} maxLength={6000} value={card.text} onChange={event => onChange({ text: event.target.value })} /><div className="deck-field-pair"><Field label={`Card ${index} weight`} inputMode="decimal" value={card.weight} onChange={event => onChange({ weight: event.target.value })} /><Field label={`Card ${index} tags`} value={card.tags} hint="Comma-separated, case-sensitive tags." onChange={event => onChange({ tags: event.target.value })} /></div><label className="check-row"><input type="checkbox" checked={card.enabled} onChange={event => onChange({ enabled: event.target.checked })} />Enable card {index} for draws</label><details><summary>Stable card ID</summary><code>{card.id}</code></details><button className="text-button" disabled={!removable} onClick={onRemove}>Remove card {index}</button></section>
}

export function DeckMetadata({ value }: { value: Record<string, unknown> }) {
  if (!Object.keys(value).length) return null
  return <details><summary>Preserved unsupported metadata · reference only</summary><pre className="deck-json">{JSON.stringify(value, null, 2)}</pre></details>
}
