import type { Branch } from '../../types'
import type { AssessmentChoice } from './assessmentTypes'

export interface MessageReceipt { branch_id: string; node_id: string }
export function continuationRequest(branch: Branch, receipt: MessageReceipt, selected: string, usePrepared: boolean, choice: AssessmentChoice) {
  if (branch.id !== receipt.branch_id || branch.head_id !== receipt.node_id) throw new Error('Your message was saved, but this path changed before continuation could start. Review the latest passage before continuing.')
  return {
    operation_id: `continue-${receipt.node_id}`, expected_revision: branch.revision,
    profile_ids: selected ? [selected] : [],
    use_prepared_beat: usePrepared && !!branch.mechanics.pending && !branch.mechanics.pending.stale,
    ...choice,
  }
}
