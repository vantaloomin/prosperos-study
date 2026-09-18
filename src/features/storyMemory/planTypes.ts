import type { ContinuityView, PlannedEvent } from '../scenes/continuityTypes'

export type PlanEntry = ContinuityView['entries'][number] & { plan: PlannedEvent }
export type PlanView = ContinuityView & { revision: number; version_id: string | null }
export interface PlanSource { id: string; text: string; title: string; node_id: string }
export const planStatuses = ['proposed', 'agreed', 'postponed', 'attempted', 'uncertain', 'completed', 'cancelled'] as const
export const commitments = ['proposed', 'agreed', 'declined', 'withdrawn', 'uncertain'] as const
