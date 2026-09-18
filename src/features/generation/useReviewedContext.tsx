import { useState } from 'react'
import type { ContextRequest } from './contextTypes'
import { contextRequestKey, reviewedInput, type ReviewedContext } from './reviewedContext'

export function useReviewedContext(branchId: string, request: ContextRequest) {
  const [reviewed, setReviewed] = useState<ReviewedContext | null>(null)
  const input = reviewedInput(branchId, request, reviewed)
  return { input, onReviewed: (fingerprint: string) => setReviewed({ key: contextRequestKey(branchId, request), fingerprint }),
    notice: input.reviewed_fingerprint ? <p className="subtle" role="status">Preview selected. Changes will be checked before sending. <button className="text-button" onClick={() => setReviewed(null)}>Clear preview selection</button></p> : null }
}
