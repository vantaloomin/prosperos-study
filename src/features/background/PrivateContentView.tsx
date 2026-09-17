import type { PrivateContent, PrivateTargets } from './interpretationTypes'

export function PrivateContentView({ content, targets }: { content: PrivateContent; targets?: PrivateTargets }) {
  const names = new Map(targets?.drives.map((item) => [item.id, item.character.name]))
  const days = new Map(targets?.hooks.map((item) => [item.id, item.day]))
  return <div className="form-stack">{content.drives.map((item, index) => <section className="prepared-card private-detail" key={item.target_id}><h3>{names.get(item.target_id) ?? `Private drive ${index + 1}`}</h3><p>{item.motive}</p><h4>Kept private</h4><p>{item.concealment}</p><h4>Observable expression</h4><p>{item.expression}</p><PrivateBasis items={item.basis} /></section>)}
    {content.hooks.map((item, index) => <section className="prepared-card private-detail" key={item.target_id}><h3>Future possibility {index + 1} · day {days.get(item.target_id) ?? 'unspecified'}</h3><p>{item.event}</p><h4>Foreshadowing</h4><p>{item.foreshadowing}</p><h4>Conditions</h4><p>{item.conditions}</p><PrivateBasis items={item.basis} /></section>)}
  </div>
}

function PrivateBasis({ items }: { items: { source_id: string; quote: string }[] }) {
  if (!items.length) return <p className="subtle">New proposed detail; no claim of prior evidence.</p>
  return <details><summary>Quoted context</summary>{items.map((item, index) => <blockquote key={index}>{item.quote}<small className="subtle">{item.source_id}</small></blockquote>)}</details>
}
