import { useLayoutEffect, useRef, useState } from 'react'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Story } from '../../types'
import { BranchMap } from './BranchMap'
import { ChatHeading } from './ChatHeading'

interface Props { story: Story; branchId: string; error?: string; onRetry: () => void; onBranch: (id: string) => void }

/** Keep the escape route usable while withholding actions for an unloaded path. */
export function PendingBranch({ story, branchId, error, onRetry, onBranch }: Props) {
  const workspace = useRef<HTMLDivElement>(null)
  useLayoutEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (document.activeElement === document.body) workspace.current?.querySelector<HTMLButtonElement>('.chat-heading button')?.focus()
    })
    return () => cancelAnimationFrame(frame)
  }, [])
  const [map, setMap] = useState(false)
  const [openedAt, setOpenedAt] = useState(0)
  const name = story.branches.find((branch) => branch.id === branchId)?.name ?? 'Selected branch'
  const openMap = () => { setOpenedAt(performance.now()); setMap(true) }
  return <div ref={workspace} className="chat-workspace" data-requested-branch={branchId}><main className="chat-main">
    <ChatHeading story={story} branchName={name} onMap={openMap} />
    {error ? <div className="page"><ErrorNotice message={error} /><button className="button" onClick={onRetry}>Try again</button></div> : <Loading label={`Opening ${name}…`} />}
  </main>{map && <BranchMap branches={story.branches} selected={branchId} onSelect={onBranch} onClose={() => setMap(false)} openedAt={openedAt} />}</div>
}
