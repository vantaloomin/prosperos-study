import { experienceChange, writingPreferences } from './setup'
import { ExperienceChoice, Participation, StoryStyle } from './WritingPreferences'
import '../../styles/onboarding.css'

export function StoryPreferences({ value, onChange }: { value: Record<string, unknown>; onChange: (next: Record<string, unknown>) => void }) {
  const preferences = writingPreferences(value)
  const patch = (next: Partial<typeof preferences>) => onChange({ ...value, ...next })
  return <div className="form-stack setup-writing-options"><p className="subtle">These preferences guide future writing and reviews. Saved passages and earlier requests keep their original contents.</p><ExperienceChoice value={preferences.experience} onChange={(experience) => patch(experienceChange(experience))} /><StoryStyle value={preferences} onChange={patch} /><Participation value={preferences} onChange={patch} /></div>
}
