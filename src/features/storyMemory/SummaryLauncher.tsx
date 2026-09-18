import { lazy, Suspense, useRef, useState } from 'react'
import { NotebookPen } from 'lucide-react'
import type { Branch } from '../../types'

const SummaryWorkspace = lazy(() => import('./SummaryWorkspace'))

export function SummaryLauncher({ branch }: { branch: Branch }) {
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement>(null)
  return <><button ref={trigger} className="text-button" onClick={() => setOpen(true)}><NotebookPen size={15} />Story memory</button>
    {open && <Suspense fallback={<p role="status">Opening Story memory…</p>}><SummaryWorkspace key={branch.id} branch={branch} onClose={() => setOpen(false)} focusOnClose={() => trigger.current} /></Suspense>}
  </>
}
