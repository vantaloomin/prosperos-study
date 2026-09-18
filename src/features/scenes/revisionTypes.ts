import type { ReviewFinding } from '../workflow/types'

export const dispositions = ['hard-fix', 'fix', 'cut', 'overrule', 'verify', 'hold', 'undecidable'] as const
export type Disposition = typeof dispositions[number]
export interface Evidence { source_id: string; quote: string }
export interface Resolution { disposition: Disposition; reason: string; action: string; evidence: Evidence[] }
export interface TriageItem extends Resolution { id: string; finding_ids: string[] }
export interface Source { id: string; title: string; text: string; kind: string }
export interface Verdict { job_id: string; verdict: string; summary: string; evidence: Evidence[]; smallest_fix: string }
export interface RevisionPlan {
  summary: string; approach: 'patch' | 'redraft'; items: TriageItem[]
  sources: Source[]; findings: (ReviewFinding & { id: string; role: string })[]
  verifications: Record<string, Verdict>; packages: Record<string, string[]>
}
export interface AvailableReport { id: string; step: string; profile_name: string; created_at: string; findings: number; preferred: boolean }
