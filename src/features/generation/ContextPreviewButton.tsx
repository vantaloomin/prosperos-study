import { lazy, Suspense, useState } from 'react'
import { ScanText } from 'lucide-react'
import type { ContextRequest } from './contextTypes'

const ContextInspector = lazy(() => import('./ContextInspector'))

export function ContextPreviewButton({ branchId, request, disabled = false, onReviewed }: { branchId: string; request: ContextRequest; disabled?: boolean; onReviewed?: (fingerprint: string) => void }) {
  const [open, setOpen] = useState(false)
  return <><button className="text-button" onClick={() => setOpen(true)} disabled={disabled}><ScanText size={15} />Context budget</button>
    {open && <Suspense fallback={<span role="status">Opening context…</span>}><ContextInspector branchId={branchId} request={request} onReviewed={onReviewed} onClose={() => setOpen(false)} /></Suspense>}</>
}
