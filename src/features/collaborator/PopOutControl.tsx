import { useEffect, useRef, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Selection } from '../../types'
import type { PrepareCompanion } from './SideComposer'
import { openCompanionWindow } from './popOutWindow'

export function PopOutControl({ selection, prepare }: { selection: Selection; prepare: PrepareCompanion }) {
  const action = useAction(), trigger = useRef<HTMLButtonElement>(null)
  const [child, setChild] = useState<Window | null>(null)
  useEffect(() => {
    if (!child) return
    const timer = window.setInterval(() => {
      if (!child.closed) return
      setChild(null)
      // A deliberate Return already focuses the conversation. Native closure
      // should restore this trigger only when focus has no other destination.
      if (document.hasFocus() && [document.body, trigger.current].includes(document.activeElement as HTMLButtonElement)) trigger.current?.focus({ preventScroll: true })
    }, 500)
    return () => window.clearInterval(timer)
  }, [child])
  const open = () => action.run(async () => {
    // Open during the click gesture, then finish saving the shared draft.
    setChild(openCompanionWindow(selection))
    await prepare.current?.()
  })
  return <div className="companion-popout-control"><button ref={trigger} type="button" className="text-button" disabled={action.busy} onClick={() => void open()}><ExternalLink size={14} />{child ? 'Show Pop Out' : 'Pop Out'}</button><ErrorNotice message={action.error} /></div>
}
