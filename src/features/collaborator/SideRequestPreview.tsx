import { Modal } from '../../components/Modal'
import { taskLabels, type CompanionWork, type WritingLabels } from './workTypes'

export interface RequestPreview {
  fingerprint: string; work: CompanionWork | null; writing: WritingLabels
  models: { name: string; number: number; provider: string; model: string; input_allowance: number; output_limit: number }[]
  input_estimate: number; max_calls: number; disclosure: string; mode: string
  sources: { id: string; title: string }[]; prompt: string; content: string; cost: null
}

export default function SideRequestPreview({ value, current, onClose, focusOnClose }: { value: RequestPreview; current: boolean; onClose: () => void; focusOnClose: () => HTMLElement | null }) {
  const work = value.work
  return <Modal open onClose={onClose} focusOnClose={focusOnClose} title="Companion request preview" description="Review the next request. Previewing does not call a model or apply text." wide>
    <div className="dialog-body companion-request-preview">
      {!current && <p role="status">The question or its settings changed. Close this preview and preview the current request.</p>}
      <p><strong>{work ? taskLabels[work.task] : 'Discuss'}</strong> · {work?.authority === 'apply' ? 'Apply one change to the pinned text target when complete' : 'Reply or editable proposal for review'}</p>
      <p>Style: {writingName(value.writing.style)}. Recipe: {writingName(value.writing.recipe)}.</p>
      <p>At most {value.max_calls} model calls, including optional source reads. Provider cost is unknown.</p>
      <p>Initial input estimate: {value.input_estimate.toLocaleString()} tokens. This estimate uses text size; provider token counts may differ.</p>
      {value.models.map((model, index) => <section key={index} aria-label="Preview model"><strong>{model.name} · v{model.number}</strong><p>{model.provider} · {model.model}</p><p>Input allowance: {model.input_allowance.toLocaleString()} tokens. Maximum output per call: {model.output_limit.toLocaleString()} tokens.</p></section>)}
      <p>{value.sources.length} permitted source sections · {value.mode === 'long' ? 'Paged Long Story archive' : 'Complete source index'} · {value.disclosure}.</p>
      <details><summary>Available source scope</summary><ul>{value.sources.map(source => <li key={source.id}>{source.title}</li>)}</ul></details>
      <details><summary>Exact first request and effective guidance</summary><h3>Instructions</h3><pre>{value.prompt}</pre><h3>Content</h3><pre>{formatContent(value.content)}</pre></details>
      <p className="subtle">Sending after this preview checks the same resolved inputs. A changed dependency requires a fresh preview. Later source reads stay within the saved scope and call limit.</p>
      <button type="button" className="button" onClick={onClose}>Return to request</button>
    </div>
  </Modal>
}

function writingName(value: WritingLabels['style']) { return value ? `${value.name} · v${value.number}` : 'None' }
function formatContent(content: string) { try { return JSON.stringify(JSON.parse(content), null, 2) } catch { return content } }
