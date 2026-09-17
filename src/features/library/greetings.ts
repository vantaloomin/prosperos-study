import type { AssetContent, CharacterGreeting } from '../../types'

export function characterGreetings(content: AssetContent): CharacterGreeting[] {
  const values = content.greetings
  return Array.isArray(values) ? values.filter((item) => item && typeof item.id === 'string' && typeof item.label === 'string' && typeof item.text === 'string') : []
}
