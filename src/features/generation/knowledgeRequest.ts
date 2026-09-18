export function characterRequest<T extends object>(request: T, subject: string) {
  if (!subject) return request
  const identity = subject.startsWith('character:') ? { knowledge_character_id: subject.slice(10) } : { knowledge_subject: subject.startsWith('name:') ? subject.slice(5) : subject }
  return { ...request, ...identity, use_prepared_beat: false, assess_beat: false, assessment_profile_ids: [] }
}
