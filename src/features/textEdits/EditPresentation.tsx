import type { TargetSnapshot, TextTarget } from './types'

const targetLabels: Record<TextTarget['kind'], string> = { passage: 'Accepted passage', candidate: 'Unaccepted prose draft', 'scene-block': 'Unaccepted scene text', 'story-brief': 'Story brief', document: 'Unsent text', 'library-field': 'Library text', 'writing-field': 'Writing resource', prompt: 'Prompt instructions' }

export function TargetCard({ target }: { target: TargetSnapshot }) {
  return <section className="text-target-card" aria-label="Selected text target"><span className="eyebrow">{targetLabels[target.ref.kind]}</span><h3>{target.label}</h3><p className="subtle">Revision {target.basis.revision}{'branch_id' in target.ref ? ` · telling ${target.ref.branch_id.slice(-8)}` : ''}{'node_id' in target.ref ? ` · passage ${target.ref.node_id.slice(-8)}` : ''}</p><TargetScope target={target.ref} /></section>
}

export function TargetScope({ target }: { target: TextTarget }) {
  if (target.kind === 'scene-block') return <SceneTextBoundary />
  if (target.kind === 'candidate') return <p className="subtle">Apply saves an author revision of this draft. The original model output stays available, and keeping the draft in the Story remains a separate action. Once kept, revise the accepted passage from the Story.</p>
  if (target.kind === 'library-field' || target.kind === 'writing-field') return <p className="subtle">Apply publishes a new shared Library edition. Existing Stories keep their pinned editions. Undo publishes another edition with the previous field text and retains independent changes to other fields.</p>
  if (target.kind !== 'prompt') return null
  if (target.workspace_id?.startsWith('restored:')) return <p className="subtle">This is a restored workspace receipt. To change a current workspace default, start a new scoped edit from its prompt editor.</p>
  return <p className="subtle">{target.prompt_scope === 'story' ? 'Apply publishes and selects a new instruction version for future requests in this Story.' : 'Apply publishes a new workspace default. Future requests in Stories that inherit this default will use it; explicitly pinned Stories keep their editions.'} Saved model requests remain unchanged. Undo publishes the previous text in the same scope.</p>
}

export function SceneTextBoundary() {
  return <p className="subtle">Apply changes this block of the selected scene draft and preserves its prose/dialogue structure. Dependent coverage, review, revision-package, patch and continuity choices must be reviewed again. Saved specialist results remain available. Keeping the scene is separate; after keeping it, revise the accepted Story passage.</p>
}

export function TextComparison({ before, after }: { before: string; after: string }) {
  return <div className="text-edit-comparison"><section><h4>Before</h4><pre>{before || '(empty)'}</pre></section><section><h4>After</h4><pre>{after || '(empty)'}</pre></section></div>
}

export function RevisionBoundary() {
  return <p className="subtle edit-boundary">Applying creates a revised telling and keeps later prose in order. Plans, summaries, character evidence, chance, and background state from this point onward remain on the source telling. The revised telling uses the state before this passage; no model calls or rolls are replayed. Review the later prose and rebuild affected memory before continuing.</p>
}
