import { ArrowUp, Dice5, PenLine } from 'lucide-react'
import type { KeyboardEvent } from 'react'
import { useEffect, useRef, useState } from 'react'
import { ErrorNotice } from '../../components/Feedback'
import { usePersistent } from '../../hooks/usePersistent'
import { useWritingActions } from '../generation/writingActions'
import type { Branch, Role } from '../../types'
import { composerCopy, composerOptions, type StoryMode } from '../stories/storyMode'
import { useComposerDraft } from './useComposerDraft'
import { useSubmission } from './useSubmission'
import { noteComposing } from './composing'
import { DocumentTools } from '../textEdits/DocumentTools'

export interface DraftTransfer { id: string; branchId: string; text: string }

interface Props { branch: Branch; mode: StoryMode; transfer?: DraftTransfer | null; onTransferred?: () => void; onRandomness: () => void }

export function Composer({ branch, mode, transfer, onTransferred, onRandomness }: Props) {
  const { onSubmitted, busy: generationBusy, canGenerate } = useWritingActions()
  const draft = useComposerDraft(branch, mode)
  const { text, role, edit, setRole } = draft
  const copy = composerCopy(mode, role)
  const [skippedBeat, setSkippedBeat] = useState('')
  const [autoContinue, setAutoContinue] = usePersistent('roleplay:auto-continue', true)
  const prepared = branch.mechanics.pending
  const narrative = role === 'narrator' || role === 'assistant'
  const useBeat = !!prepared && !prepared.stale && skippedBeat !== prepared.id && narrative
  const action = useSubmission(branch, onSubmitted, async saved => {
    // Older pending requests predate atomic draft consumption. Preserve newer
    // text, and clear only an unchanged local copy of that historical request.
    if (!saved.request.body.expected_document_version && draft.controller.getState().text === saved.request.body.text) draft.controller.edit('')
    await draft.controller.refresh()
  })
  const input = useRef<HTMLTextAreaElement>(null)
  const submitted = useRef(false)
  const applied = useRef('')
  const locked = action.busy || !!action.pending
  const sendDisabled = [!text.trim(), action.busy, generationBusy, draft.phase !== 'ready'].some(Boolean)
  useEffect(() => {
    if (!transfer || transfer.branchId !== branch.id || applied.current === transfer.id || !draft.base) return
    applied.current = transfer.id
    edit([text, transfer.text].filter(Boolean).join('\n\n'))
    input.current?.focus()
    onTransferred?.()
  }, [transfer, branch.id, text, edit, onTransferred, draft.base])
  useEffect(() => {
    if (submitted.current && !action.busy) input.current?.focus()
  }, [action.busy])
  const send = () => {
    submitted.current = true
    if ((!text.trim() || generationBusy) && !action.pending) return
    return action.send({ text, role, opportunity: useBeat ? prepared!.id : null, continue: autoContinue && canGenerate, prepare: draft.controller.flush })
  }
  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey) && text.trim()) {
      event.preventDefault()
      void send()
    }
  }
  return <div className="composer-wrap"><ErrorNotice message={action.error} /><SubmissionRecovery action={action} onCheck={() => void send()} /><PreparedNarration prepared={prepared} narrative={narrative} useBeat={useBeat} onSkip={setSkippedBeat} /><form className="composer" onSubmit={(event) => { event.preventDefault(); void send() }}>
    <textarea ref={input} aria-label="Story message" placeholder={copy.placeholder} value={text} onChange={(e) => { edit(e.target.value); noteComposing() }} onKeyDown={onKeyDown} rows={3} disabled={[locked, draft.phase === 'loading'].some(Boolean)} />
    <MessageModes mode={mode} role={role} onChange={setRole} disabled={locked} /><div className="composer-bottom"><label className="auto-continue"><input type="checkbox" checked={autoContinue} disabled={!canGenerate} onChange={event => setAutoContinue(event.target.checked)} />Continue after sending</label><span className="composer-hint">⌘ / Ctrl + Enter</span><button type="submit" className="button primary" disabled={sendDisabled}><ArrowUp size={18} />{submitLabel(copy.submit, autoContinue, canGenerate)}</button></div>
  </form><DocumentTools draft={draft} disabled={locked} inputRef={input} /><div className="composer-caption"><span>{continuationCaption(canGenerate, autoContinue, copy.caption)}</span><button onClick={onRandomness}><Dice5 size={12} />Randomness {branch.mechanics.enabled ? 'on' : 'off'}</button></div></div>
}

function submitLabel(label: string, automatic: boolean, available: boolean) { return label + (automatic && available ? ' & continue' : '') }

function MessageModes({ mode, role, onChange, disabled }: { mode: StoryMode; role: Role; onChange: (value: Role) => void; disabled: boolean }) {
  const main = mode === 'roleplay' ? 'user' : 'narrator'
  const extras = composerOptions(mode).filter(([value]) => value !== main && value !== 'ooc')
  return <fieldset className="composer-modes" aria-label="Writing mode" disabled={disabled}><button type="button" aria-pressed={role === main} onClick={() => onChange(main)}><PenLine size={14} />{mode === 'roleplay' ? 'Your character' : 'Story text'}</button><button type="button" aria-pressed={role === 'ooc'} onClick={() => onChange('ooc')}>{mode === 'roleplay' ? 'Out of character' : "Author’s note"}</button><select aria-label="More writing modes" value={extras.some(([value]) => role === value) ? role : ''} onChange={event => { if (event.target.value) onChange(event.target.value as Role) }}><option value="">More writing modes</option>{extras.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><span className="subtle">Author notes and prose keep separate unsent drafts.</span></fieldset>
}

function continuationCaption(available: boolean, automatic: boolean, fallback: string) {
  if (!available) return 'Your words are saved. Add a writing model in Settings for automatic continuation.'
  return automatic ? 'Sends your contribution, then prepares the next draft for review.' : fallback
}

function SubmissionRecovery({ action, onCheck }: { action: ReturnType<typeof useSubmission>; onCheck: () => void }) {
  if (!action.pending || action.busy) return null
  return <div className="request-recovery"><span>Check the saved action before sending this passage again.</span><button className="button" onClick={onCheck}>Check saved passage</button>{action.pending.rejected && <button className="text-button" onClick={action.editRejected}>Return to editing</button>}</div>
}

function PreparedNarration({ prepared, narrative, useBeat, onSkip }: { prepared: Branch['mechanics']['pending']; narrative: boolean; useBeat: boolean; onSkip: (id: string) => void }) {
  if (!prepared || !narrative) return null
  return <label className="prepared-choice check-row"><input type="checkbox" checked={useBeat} disabled={prepared.stale} onChange={event => onSkip(event.target.checked ? '' : prepared.id)} />Accept this narration with its prepared beat{prepared.stale && ' (outdated)'}</label>
}
