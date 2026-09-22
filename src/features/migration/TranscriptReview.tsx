import { useEffect, useRef, useState, type RefObject } from 'react'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Selection } from '../../types'
import { TranscriptMessages } from './TranscriptMessages'
import type { TranscriptPreview, TranscriptResult } from './transcriptTypes'

export function TranscriptDownloads({ id }: { id: string }) {
  return <div className="import-downloads"><a className="text-button" href={`/api/migration/transcripts/${id}/original`} download>Download original transcript</a><a className="text-button" href={`/api/migration/transcripts/${id}/report`} download>Download conversion report</a></div>
}

export function TranscriptReview({ preview, onOpen, publishChoices, hasBatchDuplicate = false, draftKey }: { preview: TranscriptPreview; onOpen: (selection: Selection) => void; publishChoices?: (choices: object) => Promise<TranscriptResult>; hasBatchDuplicate?: boolean; draftKey?: string }) {
  const [draft, setDraft] = usePersistent(draftKey ?? `roleplay:transcript-review:${preview.id}`, {
    title: preview.filename.replace(/\.[^.]+$/, '').slice(0, 120), operation: operationId(), reviewed: false, duplicate_action: 'skip',
    choices: preview.messages.map(message => ({ index: message.index, variant: 0, role: message.proposed_role })),
  })
  const [result, setResult] = useState<TranscriptResult | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [preview.id, result])
  const action = useAction()
  const selected = draft.choices.filter(choice => choice.role !== 'skip')
  const publish = () => action.run(async () => {
    const send = publishChoices ?? ((choices: object) => api<TranscriptResult>(`/migration/transcripts/${preview.id}/publish`, choices))
    setResult(await send({
      operation_id: draft.operation, source_sha256: preview.source_sha256, title: draft.title,
      reviewed: draft.reviewed, duplicate_action: draft.duplicate_action, selections: selected,
    }))
  })
  if (result) return <TranscriptSaved result={result} id={preview.id} heading={heading} onOpen={onOpen} onAgain={() => { setDraft({ ...draft, operation: operationId(), reviewed: false }); setResult(null) }} />
  return <section className="form-stack"><h3 ref={heading} tabIndex={-1}>{preview.filename}</h3><p className="subtle">{preview.format} · {preview.messages.length} messages · New Story</p><TranscriptDownloads id={preview.id} />
    <details className="import-compatibility" open><summary>Mapping and compatibility</summary><ul>{preview.notes.map(note => <li key={note}>{note}</li>)}</ul><p className="subtle">The preserved original includes all source metadata and becomes part of this Story’s private archive. Public Book exports use selected prose only.</p></details>
    <label className="field"><span>Imported Story title</span><input maxLength={120} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value, operation: operationId() })} /></label>
    {(!!preview.duplicates.length || hasBatchDuplicate) && <section className="import-compatibility"><h4>Possible duplicate imports</h4>{preview.duplicates.map(item => <p key={item.receipt_id}>{item.title} · {item.match === 'exact-source' ? 'exact original file' : 'same mapped message content; source metadata can differ'}</p>)}<label className="field"><span>Duplicate decision</span><select aria-label="Duplicate decision" value={draft.duplicate_action} onChange={event => setDraft({ ...draft, duplicate_action: event.target.value, operation: operationId(), reviewed: false })}><option value="skip">Skip if already imported</option><option value="new">Deliberately create another Story</option></select></label></section>}
    <TranscriptMessages messages={preview.messages} choices={draft.choices} onChange={choices => setDraft({ ...draft, choices, reviewed: false, operation: operationId() })} />
    <label className="check-row"><input type="checkbox" checked={draft.reviewed} onChange={event => setDraft({ ...draft, reviewed: event.target.checked })} />I reviewed the source, roles, selected messages and compatibility notes.</label>
    <ErrorNotice message={action.error} /><div className="migration-actions"><span>{selected.length} selected messages</span><button className="button primary" disabled={!selected.length || !draft.reviewed || !draft.title.trim()} aria-disabled={action.busy} onClick={publish}>{action.busy ? 'Importing…' : 'Import as a new Story'}</button></div>
  </section>
}

function TranscriptSaved({ result, id, heading, onOpen, onAgain }: { result: TranscriptResult; id: string; heading: RefObject<HTMLHeadingElement | null>; onOpen: (selection: Selection) => void; onAgain: () => void }) {
  return <section className="form-stack"><h3 ref={heading} tabIndex={-1}>{result.status === 'imported' ? 'Your imported Story is ready' : 'Duplicate left unchanged'}</h3><p>{result.status === 'imported' ? `${result.selected_messages} selected messages became a new Story. The original file and reviewed choices are preserved in Story setup.` : 'This source or equivalent mapped messages already belong to an imported Story. No new Story was created.'}</p><TranscriptDownloads id={id} />{result.story_id && <button className="button primary" onClick={() => onOpen({ storyId: result.story_id!, branchId: result.branch_id! })}>Open imported Story</button>}{result.duplicates?.map(item => <button className="button" key={item.receipt_id} onClick={() => onOpen({ storyId: item.story_id, branchId: '' })}>Open {item.title}</button>)}<button className="button" onClick={onAgain}>Review source again</button></section>
}
