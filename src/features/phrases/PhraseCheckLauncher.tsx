import { lazy, Suspense, useRef, useState } from 'react'
import { ScanText } from 'lucide-react'
import type { Branch } from '../../types'

const PhraseCheck = lazy(() => import('./PhraseCheck'))

export function PhraseCheckLauncher({ branch, onReadMessage }: { branch: Branch; onReadMessage: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement>(null)
  const reading = useRef(false)
  const read = (id: string) => { reading.current = true; setOpen(false); onReadMessage(id) }
  return <><button ref={trigger} className="text-button" onClick={() => { reading.current = false; setOpen(true) }}><ScanText size={15} />Phrase check</button>
    {open && <Suspense fallback={<p role="status">Opening phrase check…</p>}><PhraseCheck key={branch.id} branch={branch} onClose={() => setOpen(false)} onRead={read} focusOnClose={() => reading.current ? document.querySelector<HTMLElement>('[aria-label="Story history"]') : trigger.current} /></Suspense>}
  </>
}
