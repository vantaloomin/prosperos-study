import { UsageSummary } from '../../components/UsageSummary'
import { lazy, Suspense, useState } from 'react'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { TextField } from '../../components/Fields'
import { useAction } from '../../hooks/useAction'
import type { Branch, Story } from '../../types'
import { activeReply } from './types'
import type { SideReply, SideTurn } from './types'
import { ReplyContext } from './ReplyContext'
import { CompanionEditResult } from './CompanionEditResult'
import { isTextTask, taskLabels } from './workTypes'
const SourceInspector = lazy(() => import('./SourceInspector').then((module) => ({ default: module.SourceInspector })))
const RequestInputs = lazy(() => import('./SourceInspector').then((module) => ({ default: module.RequestInputs })))

interface Props { turn: SideTurn; branch: Branch; story: Story; onInsert: (text: string) => void | Promise<void>; onClose: () => void; focusReplyId?: string | null }

export function SideTurnView(props: Props) {
  const { turn } = props
  const [chosen, setChosen] = useState(props.focusReplyId ?? turn.selected_reply_id ?? '')
  const current = turn.replies.find((reply) => reply.id === chosen) ?? turn.replies[0]
  return <article className="side-turn" data-side-turn={turn.id} tabIndex={-1}><div className="side-question">{turn.question}</div>{turn.snapshot.side_work && <p className="subtle">{taskLabels[turn.snapshot.side_work.task]} · {turn.snapshot.side_work.authority === 'apply' ? 'author requested application' : 'discussion or proposal'}</p>}<p className="side-source-label">{turn.snapshot.branch.name} · revision {turn.snapshot.branch.revision} · {turn.snapshot.disclosure}</p>
    {turn.replies.length > 1 && <select aria-label="Compare collaborator replies" value={current.id} onChange={(e) => setChosen(e.target.value)}>{turn.replies.map((reply, index) => <option key={reply.id} value={reply.id}>{reply.profile.name} · {reply.status} · {index + 1}</option>)}</select>}
    <SideAnswer key={current.id} {...props} reply={current} />
    <ReplyContext turn={turn} />
    <Suspense fallback={<p className="subtle">Opening source tools…</p>}><SourceInspector turn={turn} /></Suspense>
  </article>
}

function SideAnswer({ turn, reply, branch, story, onInsert, onClose }: Props & { reply: SideReply }) {
  const action = useAction()
  const [transferring, setTransferring] = useState(false)
  const command = (kind: string) => action.run(async () => { await api(`/side-replies/${reply.id}/${kind}`, {}) })
  const sameTarget = turn.snapshot.branch.id === branch.id && turn.snapshot.branch.revision === branch.revision && turn.snapshot.story_revision === story.revision
  return <section className="side-answer"><span className="eyebrow">{reply.profile.name} · {reply.status}</span><ReplyText reply={reply} structured={!!turn.snapshot.side_work && isTextTask(turn.snapshot.side_work.task)} /><ErrorNotice message={reply.error || action.error} />
    <ReplyActions reply={reply} structured={!!reply.edit} selected={turn.selected_reply_id === reply.id} busy={action.busy} onCommand={command} onTransfer={() => setTransferring(true)} />
    <ReplyCoverage turn={turn} reply={reply} />
    {transferring && <TransferDraft text={reply.output} branch={branch} source={turn} sameTarget={sameTarget} onClose={() => setTransferring(false)} onInsert={async text => { await onInsert(text); onClose() }} />}
  </section>
}

function ReplyCoverage({ turn, reply }: { turn: SideTurn; reply: SideReply }) {
  return <details className="side-coverage"><summary>Coverage: {reply.coverage.length} of {turn.source_count} passages prepared</summary>
    <p>Sources may be included in full or in part, including discovery excerpts. Each read replaces the working source window. This does not prove successful delivery or attentive reading. Other paths appear only when included explicitly.</p>
    <pre>{reply.coverage.join('\n') || 'No passages prepared yet.'}</pre><p>{reply.usage.length} request attempt(s). Usage is included only when reported:</p>
    {reply.usage.map((usage, index) => <section key={index}><h4>Request {index + 1}</h4><UsageSummary usage={(usage.reported ?? {}) as Record<string, unknown>} /></section>)}{reply.usage.map((usage, index) => usage.content_sha256 ? <Suspense key={index} fallback={null}><RequestInputs replyId={reply.id} index={index} /></Suspense> : null)}
  </details>
}

function ReplyText({ reply, structured }: { reply: SideReply; structured: boolean }) {
  if (reply.edit) return <CompanionEditResult result={reply.edit} />
  if (structured) return <><p className="subtle">{activeReply(reply) ? 'Preparing the requested wording…' : 'No complete text proposal was saved.'}</p>{reply.output && <details><summary>Inspect preserved model output</summary><pre>{reply.output}</pre></details>}</>
  if (/^(READ|SEARCH|LIST)_SOURCES:/.test(reply.output.trimStart())) return <p className="subtle">{activeReply(reply) ? 'Consulting the frozen source archive…' : 'Source retrieval ended before an answer was ready.'}</p>
  return <div className="side-prose">{reply.output || (activeReply(reply) ? 'Working on your question…' : 'No reply text was returned.')}</div>
}

function ReplyActions({ reply, structured, selected, busy, onCommand, onTransfer }: { reply: SideReply; structured: boolean; selected: boolean; busy: boolean; onCommand: (kind: string) => void; onTransfer: () => void }) {
  if (activeReply(reply)) return <button className="button" onClick={() => onCommand('cancel')} disabled={busy}>Stop reply</button>
  if (reply.status !== 'done') return <button className="text-button" onClick={() => onCommand('retry')} disabled={busy}>Retry these inputs</button>
  return <div className="side-reply-actions">{!structured && <button className="text-button" onClick={onTransfer}>Use selected text in composer</button>}{!selected && <button className="text-button" disabled={busy} onClick={() => onCommand('select')}>Use this reply for the discussion</button>}{selected && <span className="subtle">Included in this discussion</span>}</div>
}

function TransferDraft({ text, branch, source, sameTarget, onInsert, onClose }: { text: string; branch: Branch; source: SideTurn; sameTarget: boolean; onInsert: (text: string) => void | Promise<void>; onClose: () => void }) {
  const [draft, setDraft] = useState(text)
  const action = useAction()
  const insert = () => action.run(async () => {
    const current = await api<Branch>(`/branches/${branch.id}`)
    if (current.revision !== source.snapshot.branch.revision) throw new Error('This branch has changed. Ask the collaborator to rework the suggestion against its new context.')
    const story = await api<Story>(`/stories/${current.story_id}`)
    if (story.revision !== source.snapshot.story_revision) throw new Error('Story settings changed since this suggestion. Ask for an updated suggestion first.')
    await onInsert(draft)
    onClose()
  })
  return <Modal open onClose={onClose} title="Choose what to carry over" description="Keep only the text you want to use. It will be added to your unsent draft; sending remains your choice."><div className="dialog-body form-stack"><TextField label="Text to insert" rows={10} value={draft} onChange={(e) => setDraft(e.target.value)} /><p className="subtle">Remove commentary, spoilers, and alternatives you do not want your writer to use.</p>{!sameTarget && <ErrorNotice message="This suggestion belongs to an earlier point or another path. Return to its source context, or ask for a new suggestion here." />}<ErrorNotice message={action.error} /></div><footer className="dialog-footer"><button className="button primary" disabled={!sameTarget || !draft.trim() || action.busy} onClick={insert}>Add to unsent draft</button></footer></Modal>
}
