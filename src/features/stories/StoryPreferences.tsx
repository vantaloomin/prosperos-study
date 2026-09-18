import { writingPreferences } from './setup'
import { ExperienceChoice, Participation, StoryStyle } from './WritingPreferences'
import { MemoryPreferences } from './MemoryPreferences'
import { TemplateOffer } from '../prompts/AgentTemplates'
import '../../styles/onboarding.css'

export function StoryPreferences({ value, onChange }: { value: Record<string, unknown>; onChange: (next: Record<string, unknown>) => void }) {
  const preferences = writingPreferences(value)
  const patch = (next: Partial<typeof preferences>) => onChange({ ...value, ...next })
  return <div className="form-stack setup-writing-options"><p className="subtle">These preferences guide future writing and reviews. Saved passages and earlier requests keep their original contents.</p><ExperienceChoice value={preferences.experience} onChange={(experience) => patch({ experience, ...(experience === 'roleplay' ? { player_agency: 'user' } : {}) })} /><TemplateOffer value={value} onChange={onChange} /><StoryStyle value={preferences} onChange={patch} /><Participation value={preferences} onChange={patch} /><MemoryPreferences value={value} onChange={onChange} /></div>
}
