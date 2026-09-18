export interface AgentTemplate { mode: 'active' | 'passive'; version: number; disabled: string[] }
export interface AgentSettings { disabled_prompts: string[]; agent_template: { mode: string; version: number; customized: boolean } }
export const agentMode = (experience: unknown) => experience === 'directed' || experience === 'scene' ? 'passive' : 'active'

export function templateSettings(template: AgentTemplate, disabled = template.disabled): AgentSettings {
  return { disabled_prompts: disabled, agent_template: { mode: template.mode, version: template.version, customized: [...disabled].sort().join() !== [...template.disabled].sort().join() } }
}

export function restoreAgentSettings(value: unknown): AgentSettings | undefined {
  if (!value || typeof value !== 'object') return
  const agents = value as AgentSettings
  if (!Array.isArray(agents.disabled_prompts) || !agents.disabled_prompts.every(key => typeof key === 'string')) return
  if (!['active', 'passive'].includes(agents.agent_template?.mode)) return
  return agents
}

export function matchingAgentSettings(experience: string, settings?: AgentSettings) {
  return settings?.agent_template.mode === agentMode(experience) ? settings : {}
}
