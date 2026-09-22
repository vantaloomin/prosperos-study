import { lazy, Suspense, useRef, useState, type RefObject } from 'react'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { useTextDocument } from './useTextDocument'
import { wholeText } from './types'
import { DraftRecovery } from './DraftRecovery'
import { prepareTextContext } from '../collaborator/prepareContext'
import { SendToCompanionButton } from '../collaborator/SendToCompanion'
import './textEdits.css'
import type { RecipeSelection } from '../writing/recipeRunTypes'
const TextEditWindow = lazy(() => import('./TextEditWindow').then(module => ({ default: module.TextEditWindow })))
const RecipeDialog = lazy(() => import('../writing/RecipeDialog').then(module => ({ default: module.RecipeDialog })))

type Document = ReturnType<typeof useTextDocument>
export function DocumentTools({ draft, disabled = false, inputRef }: { draft: Document; disabled?: boolean; inputRef?: RefObject<HTMLTextAreaElement | null> }) {
  const [editing, setEditing] = useState('')
  const [recipe, setRecipe] = useState<RecipeSelection | null>(null)
  const recipeTrigger = useRef<HTMLButtonElement>(null)
  const trigger = useRef<HTMLButtonElement>(null)
  const action = useAction()
  const open = () => action.run(async () => { const saved = await draft.controller.flush(); setEditing(saved.version) })
  const ready = draft.phase === 'ready' && !disabled
  const openRecipe = () => action.run(async () => {
    const input = inputRef?.current
    const selected = input && input.selectionStart !== input.selectionEnd ? { start: input.selectionStart, end: input.selectionEnd, text: draft.text.slice(input.selectionStart, input.selectionEnd) } : wholeText(draft.text)
    const saved = await draft.controller.flush()
    if (saved.text !== draft.text) throw new Error('This draft changed. Review the current wording before choosing recipe text.')
    setRecipe({ target: saved, selection: selected, action: selected.text === saved.text ? 'update' : 'replace' })
  })
  return <div className="document-tools"><DraftRecovery draft={draft} /><ErrorNotice message={action.error} />
    <div className="text-edit-actions"><SendToCompanionButton prepare={() => prepareDocumentContext(draft, inputRef?.current)} disabled={!ready || action.busy} /><button ref={trigger} type="button" className="text-button" disabled={!ready || action.busy} onClick={() => void open()}>Review a scoped text change</button><button ref={recipeTrigger} type="button" className="text-button" disabled={!ready || action.busy} onClick={() => void openRecipe()}>Run recipe</button></div>
    {editing && <Suspense fallback={<Loading label="Opening the text editor…" />}><TextEditWindow initial={{ target: draft.target, expectedVersion: editing }} onClose={() => { setEditing(''); void draft.controller.refresh() }} onBranch={() => {}} focusOnClose={() => trigger.current} /></Suspense>}
    {recipe && <Suspense fallback={<Loading label="Opening recipe setup…" />}><RecipeDialog initial={recipe} onClose={() => { setRecipe(null); void draft.controller.refresh() }} onBranch={() => {}} focusOnClose={() => recipeTrigger.current} /></Suspense>}
  </div>
}

async function prepareDocumentContext(draft: Document, input: HTMLTextAreaElement | null | undefined) {
  const selection = input ? { start: input.selectionStart, end: input.selectionEnd, text: draft.text.slice(input.selectionStart, input.selectionEnd) } : wholeText(draft.text)
  const saved = await draft.controller.flush()
  if (saved.text !== draft.text) throw new Error('This draft changed. Review its current text before choosing a selection.')
  return prepareTextContext(saved, selection)
}
