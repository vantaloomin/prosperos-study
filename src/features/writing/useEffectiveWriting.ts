import { useWritingPins, useWritingVersion } from './useWritingResources'
import type { RecipeContent, WritingChoices } from './types'

export function useEffectiveWriting(storyId: string, value: WritingChoices) {
  const pins = useWritingPins(storyId)
  const recipeId = value.recipe === 'inherit' ? pins.data?.recipe ?? 'none' : value.recipe
  const recipe = useWritingVersion(recipeId)
  const content = recipe.data?.content as RecipeContent | undefined
  const styleId = selectStyle(value.style, content?.style ?? 'inherit', pins.data?.style ?? 'none')
  const style = useWritingVersion(styleId)
  const error = [pins.error, recipe.error, style.error].find(Boolean)
  return { recipeId, recipe: recipe.data, content, styleId, style: style.data, error: error?.message }
}

function selectStyle(...choices: string[]) { return choices.find(item => item !== 'inherit') ?? 'none' }
