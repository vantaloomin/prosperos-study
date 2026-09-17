export interface AssessmentChoice { assess_beat: boolean; assessment_profile_ids: string[] }
export const defaultAssessmentChoice: AssessmentChoice = { assess_beat: true, assessment_profile_ids: [] }
export type WritingResult = { id: string; assessment_id?: never } | { assessment_id: string; id?: never }
