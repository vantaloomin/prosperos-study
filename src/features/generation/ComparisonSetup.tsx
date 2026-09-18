import { useState } from 'react'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { TextField } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import type { ModelProfile } from '../models/types'
import { AssessmentOptions } from './AssessmentOptions'
import type { AssessmentChoice, WritingResult } from './assessmentTypes'
import { ContextPreviewButton } from './ContextPreviewButton'
import { useReviewedContext } from './useReviewedContext'
import { characterRequest } from './knowledgeRequest'

export default function ComparisonSetup({ branch, profiles, usePrepared, assessmentChoice, onClose, onCreated, knowledge = '' }: { knowledge?: string; branch: Branch; profiles: ModelProfile[]; usePrepared: boolean; assessmentChoice: AssessmentChoice; onClose: () => void; onCreated: (result: WritingResult) => void }) {
  const [selected, setSelected] = useState<string[]>([])
  const [beatChoice, setBeatChoice] = useState(assessmentChoice)
  const [direction, setDirection] = useState('')
  const action = useAction()
  const toggle = (id: string) => setSelected(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id])
  const contextRequest = characterRequest({ expected_revision: branch.revision, profile_ids: selected, direction, use_prepared_beat: usePrepared, ...beatChoice }, knowledge)
  const preview = useReviewedContext(branch.id, contextRequest)
  const start = () => action.run(async () => {
    const result = await api<WritingResult>(`/branches/${branch.id}/generations`, { operation_id: operationId(), ...contextRequest, ...preview.input })
    onClose()
    onCreated(result)
  })
  return <Modal open onClose={onClose} title="A few ways this could go" description="Compare profiles using identical story context and instructions. Each selection makes one model request."><div className="dialog-body form-stack">{knowledge && <p className="subtle">Each draft uses the selected character's permitted evidence. Chance and beat assessment are excluded.</p>}<div className="asset-choices">{profiles.map((profile) => <label className="check-row" key={profile.profile_id}><input type="checkbox" checked={selected.includes(profile.profile_id)} onChange={() => toggle(profile.profile_id)} /><span>{profile.display_name ?? profile.name}<small>{profile.config.model}</small></span></label>)}</div>{!knowledge && branch.mechanics.automatic_assessment && <details><summary>Beat assessment before these drafts</summary><AssessmentOptions profiles={profiles} value={beatChoice} onChange={setBeatChoice} /></details>}<TextField label="Direction for every draft" rows={3} value={direction} onChange={(e) => setDirection(e.target.value)} placeholder="Optional: linger in this moment, focus on dialogue…" /><ContextPreviewButton branchId={branch.id} disabled={invalidComparison(selected.length, contextRequest.assessment_profile_ids.length)} request={contextRequest} onReviewed={preview.onReviewed} />{preview.notice}<p className="subtle">Nothing advances until you accept a draft. Provider usage may be billed for each request.</p><ErrorNotice message={action.error} /></div><footer className="dialog-footer"><span className="subtle">Choose 2-4 writer profiles. {!knowledge && branch.mechanics.automatic_assessment && beatChoice.assess_beat ? `Up to ${Math.max(1, beatChoice.assessment_profile_ids.length)} assessment requests first.` : ''}</span><button className="button primary" disabled={invalidComparison(selected.length, contextRequest.assessment_profile_ids.length) || action.busy} onClick={start}>Generate {selected.length} drafts</button></footer></Modal>
}

function invalidComparison(count: number, assessments: number) {
  return count < 2 || count > 4 || assessments > 4
}
