import { lazy, Suspense, useState } from 'react'
import { ErrorNotice } from '../../components/Feedback'
import { TextComparison } from '../textEdits/EditPresentation'
import type { EditInitial } from '../textEdits/types'
import { showCompanion } from './companionFocus'
import { taskLabels, type CompanionEditResult as Result } from './workTypes'
import { isCompanionWindow } from './popOutWindow'
import type { Selection } from '../../types'
const TextEditWindow = lazy(() => import('../textEdits/TextEditWindow').then(module => ({ default: module.TextEditWindow })))

export function CompanionEditResult({ result }: { result: Result }) {
  const [view, setView] = useState<EditInitial | null>(null)
  const [blocked, setBlocked] = useState(false)
  const current = [...result.proposals].reverse().find(item => item.status !== 'dismissed') ?? result.proposals.at(-1)!
  const open = (branchId: string) => {
    const selection = { storyId: result.origin.target.ref.story_id, branchId }
    setBlocked(!openResult(selection))
  }
  return <section className="companion-edit-result" aria-label="Companion text change"><p className="eyebrow">{taskLabels[result.origin.request.task]} · {current.status}</p><strong>{current.target.label}</strong><p>{current.explanation}</p>{Object.entries(result.origin.writing).map(([kind, value]) => value && <p className="subtle" key={kind}>{kind}: {value.name} · v{value.number}</p>)}<ErrorNotice message={result.error && current.status === 'conflict' ? result.error : ''} />
    <details><summary>Compare this wording</summary><TextComparison before={current.target.text} after={current.after_text} /></details>
    <button type="button" className="button" onClick={() => setView(current.receipt ? { receiptId: current.receipt.id } : { proposalId: current.id })}>{current.receipt ? 'View result & Undo' : 'Review text proposal'}</button>
    {blocked && <p role="status">The browser blocked the workspace window. <a href="/?companion_return=1" target="_blank" rel="noopener">Open the revised telling in the workspace</a>. This conversation and its unsent question stay here.</p>}
    <details><summary>Original proposed wording & source references</summary><pre>{result.origin.generated.replacement}</pre><p className="subtle">{result.origin.generated.explanation}</p><pre>{result.origin.generated.source_ids.join('\n') || 'No source IDs were cited.'}</pre><p className="subtle">Request {result.origin.request.request_ref}. Original model wording stays separate from your later corrections.</p></details>
    {view && <Suspense fallback={<p>Opening the text change…</p>}><TextEditWindow initial={view} onClose={() => setView(null)} onBranch={open} /></Suspense>}
  </section>
}

function openResult(selection: Selection) {
  if (!isCompanionWindow()) { showCompanion(selection); return true }
  localStorage.setItem('roleplay:selection', JSON.stringify(selection))
  try {
    if (window.opener && !window.opener.closed && window.opener.location.origin === window.location.origin) {
      window.opener.postMessage({ type: 'prospero:companion-return', selection }, window.location.origin)
      window.opener.focus()
      return true
    }
  } catch { /* A navigated parent is no longer a workspace destination. */ }
  return !!window.open('/?companion_return=1', '_blank')
}
