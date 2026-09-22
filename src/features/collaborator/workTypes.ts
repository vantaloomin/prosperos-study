import type { EditAction, TargetSnapshot, TextProposal } from '../textEdits/types'
import type { WritingChoices } from '../writing/types'
import type { ContextHead } from './contextTypes'

export const taskLabels = { discuss: 'Discuss', rewrite: 'Rewrite', expand: 'Expand', shorten: 'Shorten', 'change-tone': 'Change tone', 'apply-style': 'Apply style', write: 'Write new text', 'check-continuity': 'Check continuity', 'compare-tellings': 'Compare tellings' }
export type CompanionTask = keyof typeof taskLabels
export interface CompanionWork { task: CompanionTask; action: EditAction; authority: 'suggest' | 'apply'; writing?: WritingChoices }
export const discussion: CompanionWork = { task: 'discuss', action: 'replace', authority: 'suggest' }
export const isTextTask = (task: CompanionTask) => !['discuss', 'check-continuity', 'compare-tellings'].includes(task)
const proposalLabels: Partial<Record<CompanionTask, string>> = { rewrite: 'Propose a rewrite', expand: 'Propose an expansion', shorten: 'Propose shorter wording', 'change-tone': 'Propose a tone change', 'apply-style': 'Propose a style revision', write: 'Propose new text' }
const applyLabels: Partial<Record<CompanionTask, string>> = { 'apply-style': 'Restyle and apply', write: 'Write and apply' }
export const workBody = (work?: CompanionWork) => !work || work.task === 'discuss' ? {} : { work: isTextTask(work.task) ? work : { task: work.task } }
export interface CompanionEditResult {
  reply_id: string; origin_id: string; proposal_id: string; error: string; proposals: TextProposal[]
  origin: { target: TargetSnapshot; request: CompanionWork & { request_ref: string }; generated: { replacement: string; explanation: string; source_ids: string[] }; writing: WritingLabels }
}
export type WritingLabels = Record<'style' | 'recipe', { name: string; number: number } | null>

export function workPresentation(value: CompanionWork | undefined, context: ContextHead | undefined) {
  const work = value ?? discussion, editing = isTextTask(work.task)
  const caption = work.authority === 'apply' ? 'This request authorizes one scoped change' : 'Proposal for review'
  return { editing, label: editing ? textActionLabel(work) : 'Ask collaborator',
    caption: editing ? caption : 'Separate from the narrative',
    placeholder: editing ? 'Describe the wording you want for the selected target…' : 'Think out loud. Discussion stays separate from the story.',
    unavailable: editing && context?.context?.target.kind !== 'text' }
}

function textActionLabel(work: CompanionWork) {
  return work.authority === 'apply' ? (applyLabels[work.task] ?? `${taskLabels[work.task]} and apply`) : (proposalLabels[work.task] ?? 'Propose a text change')
}
