import { useState } from 'react'
import { api } from '../../api'
import { Field } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { splitTags, type DeckContent, type DeckFilters, type DeckPreview as Preview, type Eligibility } from './types'

export function DeckPreview({ content, onDraw, busy = false }: { content: DeckContent; onDraw?: (filters: DeckFilters) => void; busy?: boolean }) {
  const [tags, setTags] = useState(''), [excluded, setExcluded] = useState<string[]>([]), [seed, setSeed] = useState('preview')
  const [result, setResult] = useState<{ input: string; value: Preview } | null>(null)
  const action = useAction({ queryKey: ['inspiration', 'preview'] })
  const filters = { tags: splitTags(tags), excluded_ids: excluded }
  const input = JSON.stringify({ content, filters, seed, count: 5 })
  const shown = result?.input === input ? result.value : null
  const preview = () => action.run(async () => { setResult({ input, value: await api<Preview>('/inspiration/preview', JSON.parse(input)) }) })
  const exclude = (id: string) => setExcluded(excluded.includes(id) ? excluded.filter(value => value !== id) : [...excluded, id])
  return <section className="form-stack"><h3>Eligibility & isolated preview</h3><p>Draws use weights with replacement. Required tags must all match, with exact spelling. Excluded and disabled cards have no chance of selection.</p>
    <fieldset className="deck-controls form-stack" disabled={busy || action.busy}><Field label="Require all tags (comma-separated)" value={tags} onChange={event => setTags(event.target.value)} /><Field label="Preview seed" maxLength={200} value={seed} onChange={event => setSeed(event.target.value)} hint="This seed affects only the isolated preview. A recorded draw uses fresh randomness." />
    <DeckOdds content={content} selection={shown?.selection} excluded={excluded} onExclude={exclude} />
    <button className="button" disabled={!seed.trim()} onClick={preview}>Preview five draws</button></fieldset><ErrorNotice message={action.error} />
    {shown && <div className="form-stack"><h4>Preview only · no draw recorded</h4>{shown.results.map((row, index) => <p key={index}>{index + 1}. {row.card.title}</p>)}<p className="subtle">Preview changes no Story, saved roll, Canon or model setting.</p></div>}
    {onDraw && <button className="button primary" disabled={!shown || busy || action.busy} onClick={() => onDraw(filters)}>Record a new draw</button>}
  </section>
}

function DeckOdds({ content, selection, excluded, onExclude }: { content: DeckContent; selection?: Eligibility; excluded: string[]; onExclude: (id: string) => void }) {
  return <div className="deck-odds" role="group" aria-label="Cards and effective odds">{content.cards.map(card => {
    const row = selection?.cards.find(item => item.card_id === card.id)
    const probability = row ? row.probability.numerator / row.probability.denominator : 0
    return <div className="deck-odds-row" key={card.id}><label className="check-row"><input type="checkbox" aria-label={`Exclude ${card.title}`} checked={excluded.includes(card.id)} onChange={() => onExclude(card.id)} />Exclude {card.title || 'Untitled card'}</label><span>Weight {card.weight}{!card.enabled && ' · Disabled'}</span><small>{card.tags.join(', ') || 'No tags'}</small>{row && <><strong>{(probability * 100).toLocaleString(undefined, { maximumSignificantDigits: 4 })}% · {row.reason || 'eligible'}</strong><small>{row.probability.numerator} / {row.probability.denominator}</small><div className="deck-probability" aria-hidden="true"><span style={{ width: `${probability * 100}%` }} /></div></>}</div>
  })}</div>
}
