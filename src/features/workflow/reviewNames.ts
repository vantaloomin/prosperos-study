import type { WorkflowStep } from './types'

export function reviewRoleName(steps: WorkflowStep[], key: string) {
  const role = steps.find(step => step.key === key)
  if (role) return role.name
  return steps.flatMap(step => step.tasks ?? []).find(task => task.key === key)?.label ?? key
}
