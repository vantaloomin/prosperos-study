import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import { DeckPreview } from './DeckPreview'
import { useDeckDraw } from './useDeckDraw'
import { drawText, type Deck, type DeckDraw } from './types'

export function DeckPlay({ deck, onClose }: { deck: Deck; onClose: () => void }) {
  return <Modal open wide title={`Inspiration · ${deck.name}`} description={`Version ${deck.number}. Manual inspiration leaves Story randomness and Canon unchanged.`} onClose={onClose}><div className="dialog-body"><DeckPlayBody deck={deck} /></div><footer className="dialog-footer"><button className="button" onClick={onClose}>Done</button></footer></Modal>
}

export function InspirationPicker({ branch, onUse, onClose }: { branch: Branch; onUse: (text: string) => void; onClose: () => void }) {
  const query = useQuery({ queryKey: ['inspiration', 'decks'], queryFn: () => api<Deck[]>('/inspiration/decks') })
  const [selected, setSelected] = useState('')
  const transferred = useRef(false)
  const deck = query.data?.find(item => item.id === selected)
  const use = (draw: DeckDraw) => { transferred.current = true; onUse(drawText(draw)); onClose() }
  return <Modal open wide title="Inspiration for this Story" description="Explore a deck, record an explicit draw, then decide whether to use its text. Story randomness stays unchanged." onClose={onClose} focusOnClose={() => transferred.current ? document.querySelector<HTMLElement>('[aria-label="Story message"]') : null}><div className="dialog-body form-stack"><ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}
    <label className="field"><span>Choose a deck version</span><select aria-label="Choose a deck version" value={selected} onChange={event => setSelected(event.target.value)}><option value="">Choose a Library deck…</option>{query.data?.map(item => <option key={item.id} value={item.id}>{item.name} · v{item.number}</option>)}</select></label>{query.data?.length === 0 && <p>Create a deck or review a starter collection in Library → Inspiration.</p>}{deck && <DeckPlayBody key={`${deck.id}:${branch.id}`} deck={deck} branch={branch} onUse={use} />}</div><footer className="dialog-footer"><button className="button" onClick={onClose}>Done</button></footer></Modal>
}

function DeckPlayBody({ deck, branch, onUse }: { deck: Deck; branch?: Branch; onUse?: (draw: DeckDraw) => void }) {
  const state = useDeckDraw(deck, branch)
  return <div className="form-stack"><p>{deck.description}</p><DeckPreview content={deck.content} onDraw={deck.archived ? undefined : state.draw} busy={state.action.busy || !!state.pending} /><ErrorNotice message={state.action.error} />
    {state.pending && <section className="import-compatibility"><h3>Recover the pending draw</h3><p>The request keeps its saved version and choices. Retry to recover the same result after an interruption.</p><button className="button" disabled={state.action.busy} onClick={state.retry}>Retry saved draw</button></section>}
    <RecordedHistory state={state} branch={branch} onUse={onUse} />
  </div>
}

function RecordedHistory({ state, branch, onUse }: { state: ReturnType<typeof useDeckDraw>; branch?: Branch; onUse?: (draw: DeckDraw) => void }) {
  return <section className="form-stack"><h3>Recorded draw history</h3><ErrorNotice message={state.history.error?.message || state.receipt.error?.message} /><label className="field"><span>Recorded result</span><select aria-label="Recorded result" value={state.selected ?? ''} onChange={event => state.setSelected(event.target.value || null)}><option value="">Inspect a recorded draw…</option>{state.history.data?.map(item => <option value={item.id} key={item.id}>{new Date(item.created_at).toLocaleString()} · {item.card.title}</option>)}</select></label><p className="subtle">Draws for this version{branch ? ' on this Story path' : ''}, 100 per page. Each result is kept with its original version and odds.</p><HistoryPages state={state} />{state.receipt.data && <DrawResult draw={state.receipt.data} onUse={onUse} />}</section>
}

function HistoryPages({ state }: { state: ReturnType<typeof useDeckDraw> }) {
  return <div className="deck-actions"><button className="text-button" disabled={state.offset === 0 || state.history.isFetching} onClick={() => state.setOffset(state.offset - 100)}>Newer draws</button><span>Page {state.offset / 100 + 1}</span><button className="text-button" disabled={state.history.data?.length !== 100 || state.history.isFetching} onClick={() => state.setOffset(state.offset + 100)}>Older draws</button></div>
}

function DrawResult({ draw, onUse }: { draw: DeckDraw; onUse?: (draw: DeckDraw) => void }) {
  const action = useAction({ queryKey: ['inspiration', 'clipboard'] })
  const [copied, setCopied] = useState(false)
  return <article className="deck-card-editor form-stack"><h3>{draw.card.title}</h3><p>{draw.deck_name} · v{draw.deck_number} · Recorded {new Date(draw.created_at).toLocaleString()}</p><p className="deck-card-text">{draw.card.text}</p><details><summary>Inspect recorded eligibility and outcome</summary><pre className="deck-json">{JSON.stringify({ version_id: draw.version_id, ticket: draw.ticket, card_id: draw.card_id, selection: draw.selection }, null, 2)}</pre></details><ErrorNotice message={action.error} /><div className="deck-actions"><button className="button" onClick={() => action.run(async () => { await navigator.clipboard.writeText(drawText(draw)); setCopied(true) })}>{copied ? 'Copied' : 'Copy inspiration'}</button>{onUse && <button className="button primary" onClick={() => onUse(draw)}>Add to unsent input</button>}</div><p className="subtle">Using this text is your choice. It is not sent, accepted as prose, or added to Canon automatically.</p></article>
}
