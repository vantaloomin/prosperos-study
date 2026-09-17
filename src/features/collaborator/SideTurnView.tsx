import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { Modal } from '../../components/Modal'
import { TextField } from '../../components/Fields'
import { useAction } from '../../hooks/useAction'
import type { Branch, Story } from '../../types'
import { activeReply } from './types'
import type { SideReply, SideTurn, Source } from './types'

interface Props { turn: SideTurn; branch: Branch; story: Story; onInsert: (text: string) => void; onClose: () => void }

export function SideTurnView(props: Props) {
  const { turn } = props
  const [chosen, setChosen] = useState(turn.selected_reply_id ?? '')
  const current = turn.replies.find((reply) => reply.id === chosen) ?? turn.replies[0]
  return <article className="side-turn"><div className="side-question">{turn.question}</div><p className="side-source-label">{turn.snapshot.branch.name} · revision {turn.snapshot.branch.revision} · {turn.snapshot.disclosure}</p>
    {turn.replies.length > 1 && <select aria-label="Compare collaborator replies" value={current.id} onChange={(e) => setChosen(e.target.value)}>{turn.replies.map((reply, index) => <option key={reply.id} value={reply.id}>{reply.profile.name} · {reply.status} · {index + 1}</option>)}</select>}
    <SideAnswer key={current.id} {...props} reply={current} />
    <SourceInspector turn={turn} />
  </article>
}

function SideAnswer({ turn, reply, branch, story, onInsert, onClose }: Props & { reply: SideReply }) {
  const action = useAction()
  const [transferring, setTransferring] = useState(false)
  const command = (kind: string) => action.run(async () => { await api(`/side-replies/${reply.id}/${kind}`, {}) })
  const sameTarget = turn.snapshot.branch.id === branch.id && turn.snapshot.branch.revision === branch.revision && turn.snapshot.story_revision === story.revision
  return <section className="side-answer"><span className="eyebrow">{reply.profile.name} · {reply.status}</span><ReplyText reply={reply} /><ErrorNotice message={reply.error || action.error} />
    <ReplyActions reply={reply} selected={turn.selected_reply_id === reply.id} busy={action.busy} onCommand={command} onTransfer={() => setTransferring(true)} />
    <details className="side-coverage"><summary>Coverage: {reply.coverage.length} of {turn.source_count} passages prepared</summary><p>These passages were included in prepared requests. This does not prove successful delivery or attentive reading. Other paths appear only when included explicitly.</p><pre>{reply.coverage.join('\n') || 'No passages prepared yet.'}</pre><p>{reply.usage.length} request attempt(s). Usage is included only when reported:</p><pre>{JSON.stringify(reply.usage, null, 2)}</pre></details>
    {transferring && <TransferDraft text={reply.output} branch={branch} source={turn} sameTarget={sameTarget} onClose={() => setTransferring(false)} onInsert={(text) => { onInsert(text); onClose() }} />}
  </section>
}

function ReplyText({ reply }: { reply: SideReply }) {
  if (reply.output.trimStart().startsWith('READ_SOURCES:')) return <p className="subtle">{activeReply(reply) ? 'Consulting the frozen source archive…' : 'Source retrieval ended before an answer was ready.'}</p>
  return <div className="side-prose">{reply.output || (activeReply(reply) ? 'Working on your question…' : 'No reply text was returned.')}</div>
}

function ReplyActions({ reply, selected, busy, onCommand, onTransfer }: { reply: SideReply; selected: boolean; busy: boolean; onCommand: (kind: string) => void; onTransfer: () => void }) {
  if (activeReply(reply)) return <button className="button" onClick={() => onCommand('cancel')} disabled={busy}>Stop reply</button>
  if (reply.status !== 'done') return <button className="text-button" onClick={() => onCommand('retry')} disabled={busy}>Retry these inputs</button>
  return <div className="side-reply-actions"><button className="text-button" onClick={onTransfer}>Use selected text in composer</button>{!selected && <button className="text-button" disabled={busy} onClick={() => onCommand('select')}>Use this reply for the discussion</button>}{selected && <span className="subtle">Included in this discussion</span>}</div>
}

function SourceInspector({ turn }: { turn: SideTurn }) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const query = useQuery({ queryKey: ['side-sources', turn.id], queryFn: () => api<Source[]>(`/side-turns/${turn.id}/sources`), enabled: open })
  const matching = query.data?.filter((source) => (source.title + source.text).toLowerCase().includes(filter.toLowerCase()))
  return <details className="side-sources" onToggle={(e) => setOpen(e.currentTarget.open)}><summary>Inspect frozen sources, including hidden lore</summary><ErrorNotice message={query.error?.message} /><input aria-label="Find a source passage" placeholder="Find a source passage…" value={filter} onChange={(e) => setFilter(e.target.value)} />{matching?.map((source) => <details key={source.id}><summary>{source.title}</summary><small>{source.id}</small><pre>{source.text}</pre></details>)}</details>
}

function TransferDraft({ text, branch, source, sameTarget, onInsert, onClose }: { text: string; branch: Branch; source: SideTurn; sameTarget: boolean; onInsert: (text: string) => void; onClose: () => void }) {
  const [draft, setDraft] = useState(text)
  const action = useAction()
  const insert = () => action.run(async () => {
    const current = await api<Branch>(`/branches/${branch.id}`)
    if (current.revision !== source.snapshot.branch.revision) throw new Error('This branch has changed. Ask the collaborator to rework the suggestion against its new context.')
    const story = await api<Story>(`/stories/${current.story_id}`)
    if (story.revision !== source.snapshot.story_revision) throw new Error('Story settings changed since this suggestion. Ask for an updated suggestion first.')
    onInsert(draft)
    onClose()
  })
  return <Modal open onClose={onClose} title="Choose what to carry over" description="Keep only the text you want to use. It will be added to your unsent draft; sending remains your choice."><div className="dialog-body form-stack"><TextField label="Text to insert" rows={10} value={draft} onChange={(e) => setDraft(e.target.value)} /><p className="subtle">Remove commentary, spoilers, and alternatives you do not want your writer to use.</p>{!sameTarget && <ErrorNotice message="This suggestion belongs to an earlier point or another path. Return to its source context, or ask for a new suggestion here." />}<ErrorNotice message={action.error} /></div><footer className="dialog-footer"><button className="button primary" disabled={!sameTarget || !draft.trim() || action.busy} onClick={insert}>Add to unsent draft</button></footer></Modal>
}
