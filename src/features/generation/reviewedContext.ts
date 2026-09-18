import type { ContextRequest } from './contextTypes'

export interface ReviewedContext { key: string; fingerprint: string }

export function contextRequestKey(branchId: string, request: ContextRequest) {
  return JSON.stringify([branchId, request.expected_revision, request.profile_ids, request.direction ?? '',
    request.use_prepared_beat, request.assess_beat, request.assessment_profile_ids, request.knowledge_subject ?? '', request.knowledge_character_id ?? ''])
}

export function reviewedInput(branchId: string, request: ContextRequest, reviewed: ReviewedContext | null) {
  return reviewed?.key === contextRequestKey(branchId, request) ? { reviewed_fingerprint: reviewed.fingerprint } : {}
}
