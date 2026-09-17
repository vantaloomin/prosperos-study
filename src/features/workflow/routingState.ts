interface RoutingAssignment { primary_profile_id: string | null; step_profiles: Record<string, string> }

export function sameAssignments(left: RoutingAssignment, right: RoutingAssignment): boolean {
  if (left.primary_profile_id !== right.primary_profile_id) return false
  const entries = Object.entries(left.step_profiles)
  return entries.length === Object.keys(right.step_profiles).length && entries.every(([key, value]) => right.step_profiles[key] === value)
}
