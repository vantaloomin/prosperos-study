import type { ModelProfile } from '../models/types'

import type { AssessmentChoice } from './assessmentTypes'

export function AssessmentOptions({ profiles, value, onChange }: { profiles: ModelProfile[]; value: AssessmentChoice; onChange: (value: AssessmentChoice) => void }) {
  const toggle = (id: string) => {
    const ids = value.assessment_profile_ids
    onChange({ ...value, assessment_profile_ids: ids.includes(id) ? ids.filter((item) => item !== id) : [...ids, id] })
  }
  return <div className="form-stack"><label className="check-row"><input type="checkbox" checked={value.assess_beat} onChange={(e) => onChange({ ...value, assess_beat: e.target.checked })} /><span>Check for a completed beat before writing<small>Only completed, eligible beats can consult enabled tables. This adds a model request.</small></span></label>
    {value.assess_beat && <><p className="subtle">Leave profiles unchecked to inherit the beat assessment step. Choose one override, or 2–4 profiles to compare their assessments before choosing.</p><div className="asset-choices">{profiles.map((profile) => <label className="check-row" key={profile.profile_id}><input type="checkbox" checked={value.assessment_profile_ids.includes(profile.profile_id)} onChange={() => toggle(profile.profile_id)} /><span>{profile.display_name ?? profile.name}<small>{profile.config.model}</small></span></label>)}</div></>}
    <p className="subtle">A saved preparation is reused. Comparisons, retries, and alternate drafts keep the same chance result. Edit the step prompt in Workflow → Models by step.</p>
  </div>
}
