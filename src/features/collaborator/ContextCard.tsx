import type { CompanionContext } from './contextTypes'
import './contextCard.css'

export function ContextCard({ context }: { context: CompanionContext }) {
  const target = context.target
  return <section className="companion-target" data-context-id={context.id} aria-label="Companion target"><span className="eyebrow">PINNED COMPANION CONTEXT</span><strong>{context.story_title}</strong><span>{target.kind === 'text' ? target.snapshot.label : context.branch.name}</span><p className="subtle">{context.branch.name} · saved revision {context.branch.revision} · {context.source_count} source passages</p>
    {target.kind === 'text' && <><p className="subtle">Selected range {target.selection.start}–{target.selection.end} · {target.snapshot.ref.kind}</p><details><summary>Read selected text</summary><pre>{target.selection.text || '(Insertion point)'}</pre></details></>}
    {'comparison' in target && target.comparison && <p>{target.comparison.left.name} · r{target.comparison.left.revision}<br />compared with {target.comparison.right.name} · r{target.comparison.right.revision}</p>}
    {target.kind === 'turn' && <p className="subtle">The frozen sources of an earlier reply.</p>}
    <small>Changing the workspace does not change this target. Text changes use the task and application setting you choose below.</small>
  </section>
}
