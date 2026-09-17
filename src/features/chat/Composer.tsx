import { ArrowUp, Dice5, PenLine } from 'lucide-react'
import type { KeyboardEvent } from 'react'
import { useEffect, useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { usePersistent } from '../../hooks/usePersistent'
import { useWritingActions } from '../generation/writingActions'
import type { MessageReceipt } from '../generation/continuation'
import { useAction } from '../../hooks/useAction'
import type { Branch, Role } from '../../types'
import { composerCopy, composerOptions, type StoryMode } from '../stories/storyMode'
import { useComposerDraft } from './useComposerDraft'

export interface DraftTransfer { id: string; branchId: string; text: string }

interface Props { branch: Branch; mode: StoryMode; transfer?: DraftTransfer | null; onTransferred?: () => void; onRandomness: () => void }

export function Composer({ branch, mode, transfer, onTransferred, onRandomness }: Props) {
  const { onSubmitted, busy: generationBusy, error: generationError, canGenerate } = useWritingActions()
  const { text, role, edit, setRole, clear } = useComposerDraft(branch.id, mode)
  const copy = composerCopy(mode, role)
  const [skippedBeat, setSkippedBeat] = useState('')
  const [autoContinue, setAutoContinue] = usePersistent('roleplay:auto-continue', true)
  const prepared = branch.mechanics.pending
  const narrative = role === 'narrator' || role === 'assistant'
  const useBeat = !!prepared && !prepared.stale && skippedBeat !== prepared.id && narrative
  const action = useAction()
  const input = useRef<HTMLTextAreaElement>(null)
  const submitted = useRef(false)
  const applied = useRef('')
  useEffect(() => {
    if (!transfer || transfer.branchId !== branch.id || applied.current === transfer.id) return
    applied.current = transfer.id
    edit([text, transfer.text].filter(Boolean).join('\n\n'))
    input.current?.focus()
    onTransferred?.()
  }, [transfer, branch.id, text, edit, onTransferred])
  useEffect(() => {
    if (submitted.current && !action.busy) input.current?.focus()
  }, [action.busy])
  const send = () => action.run(async () => {
    submitted.current = true
    if (!text.trim() || generationBusy) return
    const receipt = await api<MessageReceipt>(`/branches/${branch.id}/messages`, { operation_id: operationId(), expected_revision: branch.revision, text, role, opportunity_id: useBeat ? prepared!.id : null })
    clear()
    if (autoContinue && canGenerate) await onSubmitted(receipt)
  })
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && text.trim()) {
      event.preventDefault()
      void send()
    }
  }
  return <div className="composer-wrap"><ErrorNotice message={action.error} /><ErrorNotice message={generationError ? `Continuation could not start. Your saved text is kept. ${generationError}` : ''} /><PreparedNarration prepared={prepared} narrative={narrative} useBeat={useBeat} onSkip={setSkippedBeat} /><form className="composer" onSubmit={(event) => { event.preventDefault(); void send() }}>
    <textarea ref={input} aria-label="Story message" placeholder={copy.placeholder} value={text} onChange={(e) => edit(e.target.value)} onKeyDown={onKeyDown} rows={3} disabled={action.busy || generationBusy} />
    <div className="composer-bottom"><label><PenLine size={14} /><select aria-label="Message type" value={role} onChange={(e) => setRole(e.target.value as Role)}>{composerOptions(mode).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label className="auto-continue"><input type="checkbox" checked={autoContinue} disabled={!canGenerate} onChange={event => setAutoContinue(event.target.checked)} />Continue after sending</label><span className="composer-hint">⌘ / Ctrl + Enter</span><button type="submit" className="send-button" aria-label={copy.submit} disabled={!text.trim() || action.busy || generationBusy}><ArrowUp size={20} /></button></div>
  </form><div className="composer-caption"><span>{continuationCaption(canGenerate, autoContinue, copy.caption)}</span><button onClick={onRandomness}><Dice5 size={12} />Randomness {branch.mechanics.enabled ? 'on' : 'off'}</button></div></div>
}

function continuationCaption(available: boolean, automatic: boolean, fallback: string) {
  if (!available) return 'Your words are saved. Add a writing model in Settings for automatic continuation.'
  return automatic ? 'Sends your contribution, then prepares the next draft for review.' : fallback
}

function PreparedNarration({ prepared, narrative, useBeat, onSkip }: { prepared: Branch['mechanics']['pending']; narrative: boolean; useBeat: boolean; onSkip: (id: string) => void }) {
  if (!prepared || !narrative) return null
  return <label className="prepared-choice check-row"><input type="checkbox" checked={useBeat} disabled={prepared.stale} onChange={event => onSkip(event.target.checked ? '' : prepared.id)} />Accept this narration with its prepared beat{prepared.stale && ' (outdated)'}</label>
}
