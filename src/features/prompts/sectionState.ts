export function sectionState(prompts: { enabled?: boolean }[]): 'all' | 'none' | 'mixed' {
  const enabled = prompts.filter(prompt => prompt.enabled !== false).length
  if (!enabled) return 'none'
  return enabled === prompts.length ? 'all' : 'mixed'
}
