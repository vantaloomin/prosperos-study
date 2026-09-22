import type { RngSettings } from '../mechanics/types'
import type { RecipeContent } from './types'

export type RecipeStep = RecipeContent['steps'][number]
export interface RecipeOptions {
  lenses: { key: string; name: string; focus: string; scope: 'blind' | 'informed' }[]
  tasks: { key: string; name: string }[]
  randomness_defaults: RngSettings
}
export const stepLabels: Record<RecipeStep['task'], string> = { writer: 'Draft prose', review: 'Review prose', revision: 'Revise prose' }
export const purposeHints = {
  draft: 'Start with a writing direction to create new prose. Reviews and revisions can follow the draft.',
  review: 'Start with selected prose and return review findings. Reviewing does not replace the text.',
  revise: 'Start with selected prose and propose new wording. A review can help focus the revision.',
}
