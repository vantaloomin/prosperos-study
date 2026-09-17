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

export default function ComparisonSetup({ branch, profiles, usePrepared, assessmentChoice, onClose, onCreated }: { branch: Branch; profiles: ModelProfile[]; usePrepared: boolean; assessmentChoice: AssessmentChoice; onClose: () => void; onCreated: (result: WritingResult) => void }) {
  const [selected, setSelected] = useState<string[]>([])
  const [beatChoice, setBeatChoice] = useState(assessmentChoice)
  const [direction, setDirection] = useState('')
  const action = useAction()
  const toggle = (id: string) => setSelected(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id])
  const start = () => action.run(async () => {
    const result = await api<WritingResult>(`/branches/${branch.id}/generations`, { operation_id: operationId(), expected_revision: branch.revision, profile_ids: selected, direction, use_prepared_beat: usePrepared, ...beatChoice })
    onClose()
    onCreated(result)
  })
  return <Modal open onClose={onClose} title="A few ways this could go" description="Compare profiles using identical story context and instructions. Each selection makes one model request."><div className="dialog-body form-stack"><div className="asset-choices">{profiles.map((profile) => <label className="check-row" key={profile.profile_id}><input type="checkbox" checked={selected.includes(profile.profile_id)} onChange={() => toggle(profile.profile_id)} /><span>{profile.display_name ?? profile.name}<small>{profile.config.model}</small></span></label>)}</div>{branch.mechanics.automatic_assessment && <details><summary>Beat assessment before these drafts</summary><AssessmentOptions profiles={profiles} value={beatChoice} onChange={setBeatChoice} /></details>}<TextField label="Direction for every draft" rows={3} value={direction} onChange={(e) => setDirection(e.target.value)} placeholder="Optional: linger in this moment, focus on dialogue…" /><ContextPreviewButton branchId={branch.id} disabled={selected.length < 2 || selected.length > 4 || beatChoice.assessment_profile_ids.length > 4} request={{ expected_revision: branch.revision, profile_ids: selected, direction, use_prepared_beat: usePrepared, ...beatChoice }} /><p className="subtle">Nothing advances until you accept a draft. Provider usage may be billed for each request.</p><ErrorNotice message={action.error} /></div><footer className="dialog-footer"><span className="subtle">Choose 2-4 writer profiles. {branch.mechanics.automatic_assessment && beatChoice.assess_beat ? `Up to ${Math.max(1, beatChoice.assessment_profile_ids.length)} assessment requests first.` : ''}</span><button className="button primary" disabled={selected.length < 2 || selected.length > 4 || beatChoice.assessment_profile_ids.length > 4 || action.busy} onClick={start}>Generate {selected.length} drafts</button></footer></Modal>
}
