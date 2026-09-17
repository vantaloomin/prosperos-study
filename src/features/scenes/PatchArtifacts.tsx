import type { PatchEdit } from './patchTypes'
import type { SceneResult } from './types'

export function PatchArtifact({ result }: { result: SceneResult }) {
  return <div className="form-stack"><p className="scene-summary">{result.summary}</p>
    {result.edits?.map((edit) => <PatchChange key={edit.block_id} edit={edit} />)}
    {result.edits?.length === 0 && <p className="subtle">No text edits proposed. Review the item explanations below.</p>}
    {result.checks?.map((check) => <article className="review-finding" key={check.change_id}><h4>{check.status === 'pass' ? 'Pass' : 'Needs correction'} · {check.change_id}</h4>{check.quotes.map((quote, index) => <blockquote key={index}>{quote}</blockquote>)}<p>{check.reason}</p></article>)}
    {result.resolutions?.map((item) => <div key={item.item_id}><strong>{item.item_id} · {item.status}</strong><p>{item.reason}</p></div>)}
    {result.issues?.map((issue, index) => <article className="review-finding" key={index}><h4>{issue.category}</h4><blockquote>{issue.quote}</blockquote><p>{issue.explanation}</p></article>)}
  </div>
}

export function PatchChange({ edit }: { edit: PatchEdit }) {
  return <article className="review-finding form-stack"><h4>{edit.operation} · {edit.block_id}</h4><p>{edit.reason}</p><small>Approved items: {edit.item_ids.join(', ')}</small>
    {(edit.operation === 'insert' || edit.operation === 'move') && <p>Position: {edit.anchor_id ? `after ${edit.anchor_id}` : 'start of scene'}{edit.speaker && ` · ${edit.speaker}`}</p>}
    <details className="input-inspector"><summary>Before and after</summary><h5>Before</h5><pre>{edit.before || '(new block)'}</pre><h5>After</h5><pre>{edit.after || '(removed block)'}</pre></details>
  </article>
}
