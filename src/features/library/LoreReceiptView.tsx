import { useState } from 'react'
import type { LoreAudit } from './loreTypes'

export interface LoreReceipt {
  entries: (LoreAudit & { asset_id: string; version_id: string; placement: string })[]
  after: { clock: number }; advanced: boolean; rng_enabled: boolean; draws: unknown[]
  sources: { id: string; title: string; text: string; placement: string }[]
}

export function LoreReceiptView({ receipt, label = 'Canon selected for this request' }: { receipt: LoreReceipt; label?: string }) {
  const [open, setOpen] = useState(false)
  return <details className="input-inspector" onToggle={(e) => { if (e.target === e.currentTarget) setOpen(e.currentTarget.open) }}><summary>{label}</summary>{open && <ReceiptContents receipt={receipt} />}</details>
}

function ReceiptContents({ receipt }: { receipt: LoreReceipt }) {
  const [raw, setRaw] = useState(false)
  const [filter, setFilter] = useState('')
  const entries = receipt.entries.filter((entry) => `${entry.title} ${entry.reason}`.toLocaleLowerCase().includes(filter.toLocaleLowerCase()))
  return <>
    <p className="subtle">Recorded beat {receipt.after.clock} · RNG {receipt.rng_enabled ? 'on' : 'off'} · {receipt.draws.length} draws in this record. World references do not establish character knowledge or accepted events.</p>
    <label className="field"><span>Find an entry decision</span><input type="search" value={filter} onChange={(e) => setFilter(e.target.value)} /></label>
    {entries.slice(0, 80).map((entry) => <article className="lore-result" key={`${entry.version_id}:${entry.entry_id}`}><strong>{entry.title}</strong><span className="eyebrow">{entry.included ? 'Included' : 'Excluded'} · {entry.placement}</span><p>{entry.reason}</p><small>{entry.estimated_tokens} estimated tokens{entry.roll !== null && ` · d100: ${entry.roll}`}</small></article>)}
    {entries.length > 80 && <p className="subtle">Showing 80 of {entries.length} decisions. Search to narrow the list.</p>}
    {!entries.length && <p className="subtle">No entry decisions match this view. Canon overviews remain available as world guidance.</p>}
    <details className="advanced-settings" onToggle={(e) => setRaw(e.currentTarget.open)}><summary>Exact selected prose and decision record</summary>{raw && <pre>{JSON.stringify(receipt, null, 2)}</pre>}</details>
  </>
}
