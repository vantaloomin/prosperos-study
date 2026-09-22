import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { dismissWorkspaceDialogs } from '../../components/modalEvents'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { ContextHead, ContextSource } from './contextTypes'
import type { SideThread } from './types'
import { pinCompanionFocus, showCompanion } from './companionFocus'

export interface PreparedContext { storyId: string; source: ContextSource; label: string; text?: string }

export function SendToCompanionButton({ prepare, disabled = false, label = 'Send selection to Companion' }: { prepare: () => PreparedContext | Promise<PreparedContext>; disabled?: boolean; label?: string }) {
  const action = useAction(), trigger = useRef<HTMLButtonElement>(null)
  const [source, setSource] = useState<PreparedContext | null>(null)
  return <><button ref={trigger} className="text-button" type="button" disabled={disabled || action.busy} onClick={() => void action.run(async () => setSource(await prepare()))}>{label}</button><ErrorNotice message={action.error} />
    {source && <SendToCompanion source={source} onClose={() => setSource(null)} focusOnClose={() => trigger.current} />}</>
}

function SendToCompanion({ source, onClose, focusOnClose }: { source: PreparedContext; onClose: () => void; focusOnClose: () => HTMLElement | null }) {
  const threads = useQuery({ queryKey: ['side-threads', source.storyId], queryFn: () => api<SideThread[]>(`/stories/${source.storyId}/side-conversations?include_archived=true`) })
  const [selected, setSelected] = useState(''), [name, setName] = useState('Selected text discussion')
  const created = useRef(''), action = useAction(), cache = useQueryClient()
  const send = () => action.run(async () => {
    let threadId = selected || created.current
    if (!threadId) { const thread = await api<{ id: string }>(`/stories/${source.storyId}/side-conversations`, { name }); threadId = thread.id; created.current = threadId }
    const current = await api<ContextHead>(`/side-conversations/${threadId}/context`)
    const result = await api<ContextHead>(`/side-conversations/${threadId}/context`, { operation_id: operationId(), expected_revision: current.revision, source: source.source })
    const selection = { storyId: source.storyId, branchId: result.context!.branch.id }
    cache.setQueryData(['side-context', threadId], result)
    await cache.invalidateQueries({ queryKey: ['side-threads', source.storyId] })
    pinCompanionFocus(selection, threadId); dismissWorkspaceDialogs(); showCompanion(selection)
  })
  return <Modal open wide title="Send selection to Companion" description="Choose the conversation for this exact source. Sending pins discussion context; it does not ask a model or apply a text change." onClose={onClose} focusOnClose={focusOnClose}><div className="dialog-body form-stack"><h3>{source.label}</h3>{source.text !== undefined && <label className="field"><span>Selected text</span><textarea aria-label="Text sent to Companion" readOnly rows={6} value={source.text} /></label>}
    <label className="field"><span>Destination conversation</span><select aria-label="Destination Companion conversation" value={selected} onChange={event => setSelected(event.target.value)}><option value="">Create a new conversation</option>{threads.data?.map(thread => <option key={thread.id} value={thread.id}>{thread.name}{thread.curation?.archived ? ' · archived' : ''}</option>)}</select></label>
    {!selected && <label className="field"><span>New conversation name</span><input aria-label="New Companion conversation name" value={name} maxLength={120} onChange={event => setName(event.target.value)} /></label>}
    <p className="subtle">An existing conversation keeps its unsent question and earlier replies. This action replaces its current context pin.</p><ErrorNotice message={action.error || threads.error?.message} /></div><footer className="dialog-footer"><button className="button primary" disabled={action.busy || !name.trim()} onClick={() => void send()}>Send and open Companion</button></footer></Modal>
}
