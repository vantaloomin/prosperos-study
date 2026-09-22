import { useEffect, useMemo, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch, Selection, Story } from '../../types'
import { Collaborator } from './Collaborator'
import { returnToWorkspace } from './popOutWindow'
import { popupTransfer } from './popupTransfer'
import { resolveBranch } from '../chat/branchSelection'
import type { SideThread } from './types'
import { companionFocusKey } from './companionFocus'
import type { CompanionFocus } from './contextTypes'
import './popOut.css'

function initialSelection(): Selection {
  const params = new URLSearchParams(window.location.search)
  return { storyId: params.get('story') ?? '', branchId: params.get('branch') ?? '' }
}

export function CompanionPopOut() {
  const [following] = usePersistent<Selection>('roleplay:selection', initialSelection(), true)
  const [focus] = usePersistent<CompanionFocus>(companionFocusKey, null, true)
  const selection = focus ?? following
  const query = useQuery({ queryKey: ['story', selection.storyId], queryFn: () => api<Story>(`/stories/${selection.storyId}`), enabled: !!selection.storyId, refetchInterval: 2500 })
  const branchId = resolveBranch(selection.branchId, query.data)
  const branch = useQuery({ queryKey: ['branch', branchId], queryFn: () => api<Branch>(`/branches/${branchId}`), enabled: !!branchId, refetchInterval: 2500 })
  const context = availableContext(query.data, branch.data)
  const error = query.error?.message || branch.error?.message
  return <main className="companion-popout" aria-label="Companion Pop Out">{context ? <><ErrorNotice message={error} /><PopOutContent key={context.story.id} {...context} /></> : <UnavailableTarget selection={selection} error={error} fetching={query.isFetching || branch.isFetching} />}</main>
}

function availableContext(story: Story | undefined, branch: Branch | undefined) {
  return story && branch && branch.story_id === story.id ? { story, branch } : null
}

function UnavailableTarget({ selection, error, fetching }: { selection: Selection; error?: string; fetching: boolean }) {
  const cache = useQueryClient()
  const action = useAction()
  return <><header><h1>Collaborator</h1><button className="button" disabled={action.busy} onClick={() => void action.run(() => returnToWorkspace(selection))}>Return to workspace</button></header><div className="popout-unavailable"><ErrorNotice message={error || action.error} />{fetching ? <Loading label="Opening the saved conversation…" /> : <><p>The selected Story or telling is unavailable. Your saved conversations and drafts remain in the workspace.</p><button className="button" onClick={() => void cache.invalidateQueries()}>Reconnect and check target</button></>}</div></>
}

function PopOutContent({ story, branch }: { story: Story; branch: Branch }) {
  const prepare = useRef<(() => Promise<void>) | null>(null)
  const action = useAction()
  const [threadId] = usePersistent(`roleplay:side-thread:${story.id}`, '', true)
  const thread = useQuery({ queryKey: ['side-thread', threadId], queryFn: () => api<SideThread>(`/side-conversations/${threadId}`), enabled: !!threadId, refetchInterval: 2500 })
  const transfer = useMemo(() => popupTransfer({ kind: 'document', story_id: story.id, branch_id: branch.id, purpose: 'composer' }), [story.id, branch.id])
  useEffect(() => { document.title = `${thread.data?.name || 'Collaborator'} · ${story.title} · Prospero’s Study` }, [thread.data?.name, story.title])
  const returnBack = () => void action.run(async () => { await prepare.current?.(); await returnToWorkspace({ storyId: story.id, branchId: branch.id }) })
  return <><header><div><span className="eyebrow">COMPANION · POP OUT</span><h1>{story.title}</h1></div><button className="button" disabled={action.busy} onClick={returnBack}>Return to workspace</button></header><ErrorNotice message={action.error} /><Collaborator story={story} branch={branch} onClose={returnBack} onInsert={transfer} prepare={prepare} /></>
}
