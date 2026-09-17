import { Modal } from '../../components/Modal'
import type { ModelProfile } from '../models/types'
import { AssessmentOptions } from './AssessmentOptions'
import type { AssessmentChoice } from './assessmentTypes'

export function AssessmentOptionsDialog({ open, profiles, value, onChange, onClose }: { open: boolean; profiles: ModelProfile[]; value: AssessmentChoice; onChange: (value: AssessmentChoice) => void; onClose: () => void }) {
  if (!open) return null
  return <Modal open onClose={onClose} title="Beat assessment options" description="Configure this request; the Story default stays in Randomness."><div className="dialog-body"><AssessmentOptions profiles={profiles} value={value} onChange={onChange} /></div><footer className="dialog-footer"><button className="button primary" disabled={value.assessment_profile_ids.length > 4} onClick={onClose}>Use these options</button></footer></Modal>
}
