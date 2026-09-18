import { initialConfig, type LocalReasoning, type ProfileConfig } from './types.ts'

export interface DiscoveredModel { id: string; name: string; context_tokens: number | null; max_output_tokens: number | null; limit_source: 'provider' | 'unreported'; reasoning_options?: LocalReasoning[]; reasoning_default?: LocalReasoning | null; supported_parameters?: string[]; supported_efforts?: string[] }
export interface Discovery { available: boolean; models: string[]; model_details?: DiscoveredModel[]; generated: false; note?: string }

export function discoveredSettings(model: DiscoveredModel, current: ProfileConfig): Partial<ProfileConfig> {
  return {
    model: model.id,
    reported_capabilities: { model_id: model.id, context_tokens: model.context_tokens, max_output_tokens: model.max_output_tokens, supported_parameters: model.supported_parameters ?? null, supported_efforts: model.supported_efforts ?? null },
    context_tokens: model.context_tokens ? Math.max(1024, Math.min(model.context_tokens, 2000000)) : (model.id === current.model ? current.context_tokens : initialConfig.context_tokens),
    max_output_tokens: model.max_output_tokens ? Math.max(64, Math.min(current.max_output_tokens, model.max_output_tokens)) : current.max_output_tokens,
  }
}

export function typedModelSettings(id: string, current: ProfileConfig, models: DiscoveredModel[] = []): Partial<ProfileConfig> {
  const known = models.find(model => model.id === id)
  return known ? discoveredSettings(known, current) : {
    model: id, context_tokens: id === current.model ? current.context_tokens : initialConfig.context_tokens,
    ...(id === current.model ? {} : { reported_capabilities: null }),
  }
}
