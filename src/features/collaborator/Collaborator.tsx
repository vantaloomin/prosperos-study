import { useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { MessageSquareText, Plus, X } from 'lucide-react'
import { motion } from 'motion/react'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch, Story } from '../../types'
import { SideComposer } from './SideComposer'
import { SideTurnView } from './SideTurnView'
import { activeReply } from './types'
import type { SideThread } from './types'

interface Props { story: Story; branch: Branch; onClose: () => void; onInsert: (text: string) => void }

export function Collaborator(props: Props) {
  const compact = useMediaQuery('(max-width: 1050px)')
  const transferred = useRef(false)
  const content = <Conversations {...props} onInsert={(text) => { transferred.current = true; props.onInsert(text) }} />
  const focusOnClose = () => document.querySelector<HTMLElement>(transferred.current ? '[aria-label="Story message"]' : '[aria-label="Open collaborator"]')
  if (compact) return <Modal open onClose={props.onClose} focusOnClose={focusOnClose} title="Beside the story" description="A separate conversation. Suggestions stay here until you choose to use them.">{content}</Modal>
  return <motion.aside className="collaborator-dock" aria-label="Sidebar collaborator" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.14 }}>
    <header><div><MessageSquareText size={17} /><h2>Beside the story</h2></div><button className="icon-button" aria-label="Close collaborator" onClick={() => { props.onClose(); requestAnimationFrame(() => focusOnClose()?.focus()) }}><X size={18} /></button></header>{content}
  </motion.aside>
}

function Conversations(props: Props) {
  const { story, branch } = props
  const query = useQuery({ queryKey: ['side-threads', story.id], queryFn: () => api<SideThread[]>(`/stories/${story.id}/side-conversations`) })
  const [selected, setSelected] = usePersistent(`roleplay:side-thread:${story.id}`, '')
  const action = useAction()
  const create = () => action.run(async () => {
    const result = await api<{ id: string }>(`/stories/${story.id}/side-conversations`, { name: `Notes on ${branch.name}` })
    setSelected(result.id)
  })
  return <div className="side-workspace"><div className="side-thread-picker"><select aria-label="Side conversation" value={selected} onChange={(e) => setSelected(e.target.value)}><option value="">Choose a conversation</option>{query.data?.map((thread) => <option key={thread.id} value={thread.id}>{thread.name}</option>)}</select><button className="icon-button" aria-label="New side conversation" onClick={create} disabled={action.busy}><Plus size={17} /></button></div><ErrorNotice message={action.error || query.error?.message} />
    {selected ? <Conversation key={selected} {...props} id={selected} /> : <div className="side-welcome"><MessageSquareText size={26} /><h3>A little room to think.</h3><p>Explore an idea, review a scene, or improve your next line. This conversation cannot progress your story.</p><button className="button primary" onClick={create} disabled={action.busy}>Start a side conversation</button></div>}
  </div>
}

function Conversation({ id, story, branch, onInsert, onClose }: Props & { id: string }) {
  const query = useQuery({ queryKey: ['side-thread', id], queryFn: () => api<SideThread>(`/side-conversations/${id}`),
    refetchInterval: (current) => current.state.data?.turns.some((turn) => turn.replies.some(activeReply)) ? 750 : false })
  const working = query.data?.turns.some((turn) => turn.replies.some(activeReply)) ?? false
  return <><div className="side-context-badge"><span>Following {branch.name} · revision {branch.revision}</span><small>Each reply keeps the context it started with.</small></div><ErrorNotice message={query.error?.message} />
    <div className="side-transcript" aria-label="Side conversation messages">{query.data?.turns.map((turn) => <SideTurnView key={turn.id} turn={turn} branch={branch} story={story} onInsert={onInsert} onClose={onClose} />)}</div>
    <SideComposer key={`${id}:${branch.id}`} threadId={id} branch={branch} story={story} working={working} />
  </>
}
